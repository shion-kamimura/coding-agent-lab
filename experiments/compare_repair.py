"""両SDKを同じ課題で各3回実行する。有料APIを使用する。"""

import asyncio
import json
import time
from unittest.mock import patch

from anthropic.resources.messages import Messages
from claude_agent_sdk import ClaudeSDKClient, ResultMessage

from coding_agent import client_repair, repair_demo


def main() -> None:
    create = Messages.create
    receive = ClaudeSDKClient.receive_response
    records = []

    async def agent_receive(self):
        async for message in receive(self):
            if isinstance(message, ResultMessage):
                records.append(
                    {
                        "turns": message.num_turns,
                        "usage": message.usage,
                        "result": message.subtype,
                    }
                )
            yield message

    def client_create(self, *args, **kwargs):
        message = create(self, *args, **kwargs)
        records.append(
            {"usage": message.usage.model_dump(), "stop": message.stop_reason}
        )
        return message

    for repeat in range(1, 4):
        order = ("client", "agent") if repeat % 2 else ("agent", "client")
        for kind in order:
            records.clear()
            start = time.monotonic()
            error = None
            try:
                if kind == "client":
                    with patch.object(Messages, "create", client_create):
                        answer = client_repair.repair()
                else:
                    with patch.object(
                        ClaudeSDKClient, "receive_response", agent_receive
                    ):
                        answer = asyncio.run(repair_demo.repair())
                success = "固定テスト4件成功" in answer
            except Exception as failure:
                success = False
                error = type(failure).__name__
            print(
                json.dumps(
                    {
                        "repeat": repeat,
                        "sdk": kind,
                        "success": success,
                        "elapsed": round(time.monotonic() - start, 2),
                        "metadata": list(records),
                        "error": error,
                    }
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
