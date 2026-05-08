#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主程序：抖音评论定向筛选与分析工具
"""

import sys
import os
import questionary
import pandas as pd

import config as cfg
import db_utils as db
from detection import detect_harassment_with_backup   # 关键修复
import file_utils as fu


def clear_config_command():
    """处理 --clearconfig 命令"""
    print("警告：此操作将删除配置文件 config.json，下次运行需要重新配置全部信息。")
    confirm = questionary.text("确定要执行吗？(yes/no): ").ask()
    if confirm and confirm.strip().lower() == "yes":
        if os.path.exists(cfg.CONFIG_FILE):
            os.remove(cfg.CONFIG_FILE)
            print("已删除配置文件。")
        else:
            print("配置文件不存在。")
        print("已完成清除，请重新运行程序进行配置。")
    else:
        print("未清除配置。")
    sys.exit(0)


def main():
    # ---------- 命令处理 ----------
    if len(sys.argv) > 1 and sys.argv[1] == "--clearconfig":
        clear_config_command()

    # ---------- 加载配置 ----------
    config = cfg.load_config()
    if not os.path.exists(cfg.CONFIG_FILE):
        print("首次运行，进入配置向导...\n")
        config = cfg.setup_wizard(config)
        cfg.save_config(config)

    print("\n当前配置概要：")
    print(f"MySQL: {config['mysql_host']}:{config['mysql_port']}, user={config['mysql_user']}")
    print(f"默认检测方法: {config['harassment_method']}")
    print(f"LLM 模型: {config['llm_model']}")
    if config.get("last_database"):
        print(f"上次数据库: {config['last_database']}.{config.get('last_table', '')}")

    if questionary.confirm("是否重新配置所有设置？", default=False).ask():
        config = cfg.setup_wizard(config)
        cfg.save_config(config)

    # ---------- 连接 MySQL ----------
    try:
        conn = db.connect_mysql(config)
        print("MySQL 连接成功")
    except Exception as e:
        print(f"连接 MySQL 失败：{e}")
        fu.log_error("MySQL 连接失败", e)
        sys.exit(1)

    # ---------- 选择数据库和表 ----------
    databases = db.get_databases(conn)
    if not databases:
        print("未发现可用数据库")
        sys.exit(1)
    last_db = config.get("last_database")
    default_db = last_db if last_db in databases else databases[0]
    selected_db = questionary.select("请选择数据库：", choices=databases, default=default_db).ask()
    if not selected_db:
        sys.exit(1)

    tables = db.get_tables(conn, selected_db)
    if not tables:
        print(f"数据库 {selected_db} 中没有表")
        sys.exit(1)
    last_tbl = config.get("last_table")
    default_tbl = last_tbl if last_tbl in tables else tables[0]
    selected_tbl = questionary.select(f"请选择数据库 {selected_db} 中的表：", choices=tables, default=default_tbl).ask()
    if not selected_tbl:
        sys.exit(1)

    config["last_database"] = selected_db
    config["last_table"] = selected_tbl
    cfg.save_config(config)

    print(f"正在读取表 {selected_db}.{selected_tbl} 的全部数据...")
    df = db.read_table_to_dataframe(conn, selected_db, selected_tbl)
    conn.close()
    print(f"读取完毕，共 {len(df)} 行")

    required_cols = ["user_id", "sec_uid", "short_user_id", "nickname", "comment_id", "parent_comment_id", "content"]
    for col in required_cols:
        if col not in df.columns:
            raise KeyError(f"表中缺少必需列：{col}")

    # ---------- 指定目标用户 ----------
    id_type = questionary.select(
        "请选择用哪种 ID 定位目标用户：",
        choices=["user_id", "sec_uid", "short_user_id"]
    ).ask()
    user_input = questionary.text(f"请输入目标用户的 {id_type}：").ask().strip()
    if not user_input:
        print("未输入用户 ID，退出")
        sys.exit(1)

    mask_user = df[id_type].astype(str) == user_input
    if not mask_user.any():
        print("未找到该用户")
        sys.exit(1)
    target_nick = df.loc[mask_user, "nickname"].iloc[0]
    if pd.isna(target_nick) or target_nick == "":
        target_nick = "未知用户"
    print(f"目标用户：{target_nick}")

    os.makedirs(config["output_dir"], exist_ok=True)

    # ---------- 1. 提取目标用户评论 ----------
    target_df = df[mask_user].copy()
    output_user_comments = os.path.join(config["output_dir"], f"{target_nick}评论内容.xlsx")
    try:
        fu.save_excel(target_df, output_user_comments, config)
    except Exception as e:
        fu.log_error("保存目标用户评论失败", e)
        fu.clean_generated_files()
        sys.exit(1)

    # ---------- 2. 排除目标用户的非空评论 ----------
    all_valid_mask = df["content"].notna() & (df["content"].astype(str).str.strip() != "")
    other_valid_mask = all_valid_mask & ~mask_user
    other_df = df[other_valid_mask].copy()
    total_other_valid = len(other_df)
    print(f"全表非空评论总数（排除目标用户）：{total_other_valid}")

    # ---------- 3. 骚扰检测 ----------
    try:
        print("\n开始骚扰内容检测...")
        harassment_df = detect_harassment_with_backup(    # 直接调用函数
            other_df, config, config["harassment_method"]
        )
    except Exception as e:
        fu.log_error("骚扰检测失败", e)
        fu.clean_generated_files()
        print("所有方法调用失败，程序终止。")
        sys.exit(1)

    harassment_series = harassment_df["is_harassment"]
    llm_response_series = harassment_df["llm_response"]
    llm_reasoning_series = harassment_df["llm_reasoning"]

    other_df["is_harassment"] = harassment_series
    harassment_count = harassment_series.sum()
    harassment_ratio = harassment_count / total_other_valid * 100 if total_other_valid > 0 else 0
    print(f"检测到骚扰评论数：{harassment_count}，占比：{harassment_ratio:.2f}%")

    # ---------- 输出 LLM 详情 ----------
    detail_cols = ["user_id", "nickname", "comment_id", "content", "parent_comment_id"]
    detail_df = other_df[detail_cols].copy()
    detail_df["response"] = llm_response_series.values
    detail_df["reasoning"] = llm_reasoning_series.values
    detail_output = os.path.join(config["output_dir"], f"{target_nick}骚扰检测详情.xlsx")
    fu.save_excel(detail_df, detail_output, config)

    # ---------- 4. 对话提取 ----------
    target_replies = target_df[target_df["parent_comment_id"].notna()].copy()
    target_replies["parent_comment_id"] = target_replies["parent_comment_id"].astype(str)

    harassment_comments = other_df[other_df["is_harassment"]].copy()
    harassment_comments["comment_id"] = harassment_comments["comment_id"].astype(str)

    replied_harass_ids = set(harassment_comments["comment_id"]).intersection(set(target_replies["parent_comment_id"]))
    print(f"收到目标用户回复的骚扰评论个数（去重）：{len(replied_harass_ids)}")

    dialogue_rows = []
    for hid in replied_harass_ids:
        parent_row = harassment_comments[harassment_comments["comment_id"] == hid].iloc[0]
        parent_copy = parent_row.to_dict()
        parent_copy["角色"] = "父评论（骚扰）"
        dialogue_rows.append(parent_copy)
        child_entries = target_replies[target_replies["parent_comment_id"] == hid]
        for _, child_row in child_entries.iterrows():
            child_copy = child_row.to_dict()
            child_copy["角色"] = "子评论（目标用户回复）"
            dialogue_rows.append(child_copy)

    dialogue_df = pd.DataFrame(dialogue_rows)
    if not dialogue_df.empty:
        cols = dialogue_df.columns.tolist()
        cols.insert(0, cols.pop(cols.index("角色")))
        dialogue_df = dialogue_df[cols]
        output_dialogue = os.path.join(config["output_dir"], f"{target_nick}回复评论及原评论内容.xlsx")
        fu.save_excel(dialogue_df, output_dialogue, config)
    else:
        print("没有符合条件的对话，不生成对话 Excel。")

    # ---------- 5. 统计报告 ----------
    target_total = len(target_df)
    target_reply_total = len(target_replies)
    unique_harass_replied = len(replied_harass_ids)
    ratio_replied_harass = (unique_harass_replied / harassment_count * 100) if harassment_count > 0 else 0
    target_reply_harass = len(target_replies[target_replies["parent_comment_id"].isin(replied_harass_ids)])
    ratio_target_reply_harass = (target_reply_harass / target_reply_total * 100) if target_reply_total > 0 else 0

    if replied_harass_ids:
        reply_counts = target_replies[target_replies["parent_comment_id"].isin(replied_harass_ids)].groupby("parent_comment_id").size()
        avg_replies_per_harass = reply_counts.mean()
    else:
        avg_replies_per_harass = 0

    report = pd.DataFrame([
        {"指标": "目标用户昵称", "值": target_nick},
        {"指标": "目标用户 ID 类型", "值": id_type},
        {"指标": "目标用户 ID 值", "值": user_input},
        {"指标": "目标用户总评论数", "值": target_total},
        {"指标": "目标用户回复评论数", "值": target_reply_total},
        {"指标": "全表非空评论数（排除目标用户）", "值": total_other_valid},
        {"指标": "骚扰评论总数", "值": harassment_count},
        {"指标": "骚扰评论占比（排除目标用户）", "值": f"{harassment_ratio:.2f}%"},
        {"指标": "被目标用户回复的骚扰评论数（去重）", "值": unique_harass_replied},
        {"指标": "被回复的骚扰评论占比", "值": f"{ratio_replied_harass:.2f}%"},
        {"指标": "目标用户回复骚扰评论的次数", "值": target_reply_harass},
        {"指标": "目标用户回复中骚扰评论占比", "值": f"{ratio_target_reply_harass:.2f}%"},
        {"指标": "平均每个骚扰评论被目标用户回复次数", "值": f"{avg_replies_per_harass:.2f}"},
    ])

    output_report = os.path.join(config["output_dir"], f"{target_nick}评论回复分析.xlsx")
    fu.save_excel(report, output_report, config)

    print("\n===== 分析完成 =====")
    print(report.to_string(index=False))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"程序异常退出：{e}")
        fu.log_error("未捕获的致命错误", e)
        fu.clean_generated_files()
        sys.exit(1)