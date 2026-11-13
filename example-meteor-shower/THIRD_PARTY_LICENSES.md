# 第三方依赖和许可（2026-11-13 核对）

本仓库自己的代码和数据用 MIT（见 `LICENSE`）。下面这些都**没有打包进来**，只是运行时需要，各自按自己的许可证使用：

| 依赖 | 用在哪 | 许可证 | 核对依据 |
|---|---|---|---|
| Qwen2.5-1.5B-Instruct（权重，Q4_K_M GGUF） | 造句的模型（`tools/`） | Apache-2.0 | Hugging Face 模型页元数据 `license: apache-2.0`（Qwen/Qwen2.5-1.5B-Instruct） |
| Ollama 0.40.16 | 本地跑模型（`tools/offline_run.sh`） | MIT | github.com/ollama/ollama 的 LICENSE |
| numpy | `render/` | BSD-3-Clause（wheel 里另含 0BSD / MIT / Zlib / CC0-1.0 组件） | 已安装包 numpy 2.5.4 的元数据 License-Expression |
| Pillow | `render/` | MIT-CMU（HPND） | 已安装包 Pillow 13.0.0 的元数据 License-Expression |
| ffmpeg | `render/` 导出 mp4（可选，作为外部程序调用） | LGPL-2.1+；带 `--enable-gpl` 编译的版本是 GPL-2.0+ | ffmpeg.org/legal.html；本仓库只调用命令行，不链接、不分发 |
| 字体（如 Noto Sans / DejaVu Sans） | `render/` 显示文字，由使用者自己提供 | Noto：SIL OFL 1.1；DejaVu：Bitstream Vera 衍生许可 | 不随仓库分发 |

模型权重不在包里。使用 Qwen2.5 权重时请遵守 Apache-2.0（保留许可证和声明）。
