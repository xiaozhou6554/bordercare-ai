from __future__ import annotations

import json
import os
import sys

import uvicorn

from scr.infrastructure.container import build_container


def cli() -> None:
    agent, registry, _ = build_container()
    print("跨境电商选品调研 Agent · 输入 /help 查看命令")
    while True:
        try:
            text = input("\n选品 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出")
            break
        if not text:
            continue
        if text in {"/exit", "/quit"}:
            break
        if text == "/help":
            print("命令：/help /tools /cache /clear /exit")
        elif text == "/tools":
            print("market_overview · trend_analyzer · category_explorer · competitor_analysis · review_miner · keyword_research · profit_calculator · supplier_search · product_scorer")
        elif text == "/cache":
            print(json.dumps(registry.cache.stats(), ensure_ascii=False))
        elif text == "/clear":
            registry.cache.clear()
            print("缓存已清空")
        else:
            try:
                print(agent.research(text).report_markdown)
            except Exception:
                print("处理失败。请检查输入后重试。")


if __name__ == "__main__":
    if "--cli" in sys.argv:
        cli()
    else:
        uvicorn.run("scr.api:app", host="127.0.0.1", port=int(os.getenv("API_PORT", "8000")), reload=False)
