"""Tkinter desktop app for wechat-digest."""

from __future__ import annotations

import threading
import tkinter as tk
import os
from datetime import datetime
from tkinter import messagebox, ttk

import config_manager
import extractor
import sender
import summarizer

WINDOW_TITLE = "微信群日报 · wechat-digest"
WINDOW_SIZE = "500x680"

PROVIDER_OPTIONS = ["Anthropic (Claude)", "OpenAI Compatible"]
PROVIDER_VALUE_MAP = {
    "Anthropic (Claude)": "anthropic",
    "OpenAI Compatible": "openai_compatible",
}
VALUE_PROVIDER_MAP = {value: key for key, value in PROVIDER_VALUE_MAP.items()}

REPORT_OPTIONS = ["今天", "今天 + 昨天", "最近 3 天", "最近 7 天"]
REPORT_DAYS_MAP = {
    "今天": 1,
    "今天 + 昨天": 2,
    "最近 3 天": 3,
    "最近 7 天": 7,
}
DAYS_REPORT_MAP = {value: key for key, value in REPORT_DAYS_MAP.items()}

MODEL_TOOLTIP_TEXT = (
    "Claude: claude-sonnet-4-20250514\n"
    "DeepSeek: deepseek-chat\n"
    "通义千问: qwen-max\n"
    "Ollama: ollama/llama3"
)

WECHAT_MOCK_ENV = "WECHAT_DIGEST_MOCK"


class ToolTip:
    """Simple tooltip for tkinter widgets."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip_window: tk.Toplevel | None = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _event: tk.Event | None = None) -> None:
        if self.tip_window:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            self.tip_window,
            text=self.text,
            justify="left",
            bg="#fffde7",
            relief="solid",
            borderwidth=1,
            padx=6,
            pady=4,
            font=("Microsoft YaHei UI", 9),
        )
        label.pack()

    def hide(self, _event: tk.Event | None = None) -> None:
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class CollapsibleSection(tk.Frame):
    """Reusable collapsible section with a clickable title bar."""

    def __init__(
        self,
        master: tk.Widget,
        title: str,
        default_expanded: bool = False,
    ) -> None:
        super().__init__(master, bd=1, relief="groove", padx=8, pady=6)
        self.title = title
        self.expanded = default_expanded

        self.header_button = tk.Button(
            self,
            text="",
            anchor="w",
            relief="flat",
            command=self.toggle,
            font=("Microsoft YaHei UI", 10, "bold"),
        )
        self.header_button.pack(fill="x")

        self.body = tk.Frame(self)
        if self.expanded:
            self.body.pack(fill="x", pady=(8, 0))

        self._update_header()

    def toggle(self) -> None:
        self.expanded = not self.expanded
        if self.expanded:
            self.body.pack(fill="x", pady=(8, 0))
        else:
            self.body.pack_forget()
        self._update_header()

    def _update_header(self) -> None:
        arrow = "▼" if self.expanded else "▶"
        self.header_button.config(text=f"{self.title} {arrow}")


class WechatDigestApp:
    """Main Tkinter app."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.all_groups: list[str] = []
        self.groups_loaded = False

        self.provider_var = tk.StringVar(value=PROVIDER_OPTIONS[0])
        self.base_url_var = tk.StringVar()
        self.ai_api_key_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.ai_test_result_var = tk.StringVar()

        self.telegram_token_var = tk.StringVar()
        self.telegram_chat_id_var = tk.StringVar()
        self.telegram_test_result_var = tk.StringVar()

        self.report_label_var = tk.StringVar(value=REPORT_OPTIONS[0])
        self.date_preview_var = tk.StringVar()
        self.group_count_var = tk.StringVar(value="共 0 个群 · 已选 0 个")

        self._build_ui()
        self._restore_config_with_safe_guard()
        self._load_groups_async(initial=True)

    def _build_ui(self) -> None:
        main_frame = tk.Frame(self.root, padx=10, pady=10)
        main_frame.pack(fill="both", expand=True)

        self.ai_section = CollapsibleSection(main_frame, "⚙ AI 模型设置", default_expanded=False)
        self.ai_section.pack(fill="x", pady=(0, 8))
        self._build_ai_section(self.ai_section.body)

        self.telegram_section = CollapsibleSection(main_frame, "📨 Telegram 设置", default_expanded=False)
        self.telegram_section.pack(fill="x", pady=(0, 8))
        self._build_telegram_section(self.telegram_section.body)

        groups_frame = tk.Frame(main_frame, bd=1, relief="groove", padx=8, pady=8)
        groups_frame.pack(fill="x", pady=(0, 8))
        self._build_group_section(groups_frame)

        export_frame = tk.Frame(main_frame, bd=1, relief="groove", padx=8, pady=8)
        export_frame.pack(fill="both", expand=True)
        self._build_export_section(export_frame)

    def _build_ai_section(self, frame: tk.Frame) -> None:
        tk.Label(frame, text="Provider", anchor="w").pack(fill="x")
        provider_combo = ttk.Combobox(
            frame,
            textvariable=self.provider_var,
            values=PROVIDER_OPTIONS,
            state="readonly",
            height=2,
        )
        provider_combo.pack(fill="x", pady=(2, 8))
        provider_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_provider_change())

        tk.Label(frame, text="Base URL", anchor="w").pack(fill="x")
        self.base_url_entry = tk.Entry(frame, textvariable=self.base_url_var)
        self.base_url_entry.pack(fill="x", pady=(2, 8))

        tk.Label(frame, text="API Key", anchor="w").pack(fill="x")
        self.ai_api_key_entry = tk.Entry(frame, textvariable=self.ai_api_key_var, show="*")
        self.ai_api_key_entry.pack(fill="x", pady=(2, 8))
        self.ai_api_key_entry.bind("<<Paste>>", self._on_api_key_paste)

        model_row = tk.Frame(frame)
        model_row.pack(fill="x")
        tk.Label(model_row, text="Model", anchor="w").pack(side="left")
        hint_label = tk.Label(model_row, text=" ? ", fg="#1e88e5", cursor="question_arrow")
        hint_label.pack(side="left")
        ToolTip(hint_label, MODEL_TOOLTIP_TEXT)

        tk.Entry(frame, textvariable=self.model_var).pack(fill="x", pady=(2, 8))

        button_row = tk.Frame(frame)
        button_row.pack(fill="x")
        tk.Button(button_row, text="保存配置", command=self.save_ai_config).pack(side="left")
        tk.Button(button_row, text="测试连接", command=self.test_ai_connection).pack(side="left", padx=(8, 8))
        tk.Label(button_row, textvariable=self.ai_test_result_var, fg="#555").pack(side="left")

    def _build_telegram_section(self, frame: tk.Frame) -> None:
        tk.Label(frame, text="Bot Token", anchor="w").pack(fill="x")
        tk.Entry(frame, textvariable=self.telegram_token_var).pack(fill="x", pady=(2, 8))

        tk.Label(frame, text="Chat ID", anchor="w").pack(fill="x")
        tk.Entry(frame, textvariable=self.telegram_chat_id_var).pack(fill="x", pady=(2, 8))

        row = tk.Frame(frame)
        row.pack(fill="x")
        tk.Button(row, text="保存配置", command=self.save_telegram_config).pack(side="left")
        tk.Button(row, text="测试连接", command=self.test_telegram_connection).pack(side="left", padx=(8, 8))
        tk.Label(row, textvariable=self.telegram_test_result_var, fg="#555").pack(side="left")

    def _build_group_section(self, frame: tk.Frame) -> None:
        header = tk.Frame(frame)
        header.pack(fill="x")
        tk.Label(header, text="💬 选择群聊", font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        tk.Button(header, text="刷新列表", command=lambda: self._load_groups_async(initial=False)).pack(side="right")

        list_row = tk.Frame(frame)
        list_row.pack(fill="x", pady=(8, 6))
        self.group_listbox = tk.Listbox(list_row, height=8, selectmode=tk.EXTENDED, exportselection=False)
        self.group_listbox.pack(side="left", fill="x", expand=True)
        self.group_listbox.bind("<<ListboxSelect>>", self._on_group_selection_change)

        scrollbar = tk.Scrollbar(list_row, orient="vertical", command=self.group_listbox.yview)
        scrollbar.pack(side="left", fill="y")
        self.group_listbox.config(yscrollcommand=scrollbar.set)

        tk.Label(frame, textvariable=self.group_count_var, fg="#666").pack(anchor="w")

    def _build_export_section(self, frame: tk.Frame) -> None:
        tk.Label(frame, text="📋 导出日报", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")

        range_row = tk.Frame(frame)
        range_row.pack(fill="x", pady=(8, 8))
        tk.Label(range_row, text="时间范围").pack(side="left")
        range_combo = ttk.Combobox(
            range_row,
            textvariable=self.report_label_var,
            values=REPORT_OPTIONS,
            state="readonly",
            width=14,
        )
        range_combo.pack(side="left", padx=(8, 8))
        range_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_report_range_change())
        tk.Label(range_row, textvariable=self.date_preview_var, fg="#666").pack(side="left")

        self.run_button = tk.Button(
            frame,
            text="🚀 生成并发送日报",
            height=2,
            command=self.generate_and_send,
            bg="#43a047",
            fg="white",
        )
        self.run_button.pack(fill="x", pady=(4, 8))

        self.log_text = tk.Text(frame, height=6, state="disabled")
        self.log_text.pack(fill="both", expand=True)

    def _restore_config_with_safe_guard(self) -> None:
        try:
            config = config_manager.load_config()
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"读取配置失败：{exc}")
            config = {}

        ai = config.get("ai", {}) if isinstance(config.get("ai"), dict) else {}
        provider_value = str(ai.get("provider") or "anthropic")
        provider_label = VALUE_PROVIDER_MAP.get(provider_value, PROVIDER_OPTIONS[0])
        self.provider_var.set(provider_label)
        self.base_url_var.set(str(ai.get("base_url") or "https://api.anthropic.com"))
        self.ai_api_key_var.set(str(ai.get("api_key") or ""))
        self.model_var.set(str(ai.get("model") or "claude-sonnet-4-20250514"))

        self.telegram_token_var.set(str(config.get("telegram_bot_token") or ""))
        self.telegram_chat_id_var.set(str(config.get("telegram_chat_id") or ""))

        report_days = int(config.get("report_days") or 1)
        self.report_label_var.set(DAYS_REPORT_MAP.get(report_days, REPORT_OPTIONS[0]))
        self._refresh_date_preview()
        self._on_provider_change(save=False)

    def _load_groups_async(self, initial: bool) -> None:
        self.group_listbox.delete(0, tk.END)
        self.group_listbox.insert(tk.END, "正在加载...")
        self.group_listbox.config(state="disabled")
        if not initial:
            self._append_log("正在刷新群聊列表...")

        def worker() -> None:
            try:
                groups = extractor.get_all_groups()
                err = ""
            except Exception as exc:  # noqa: BLE001
                groups = []
                err = str(exc)

            self.root.after(0, lambda: self._on_groups_loaded(groups, err))

        threading.Thread(target=worker, daemon=True).start()

    def _on_groups_loaded(self, groups: list[str], error: str) -> None:
        self.group_listbox.config(state="normal")
        self.group_listbox.delete(0, tk.END)

        if error:
            self.group_listbox.insert(tk.END, "加载失败")
            self.group_listbox.config(state="disabled")
            self.all_groups = []
            self.groups_loaded = False
            self._append_log(f"加载群聊失败：{error}")
            self._update_group_counter()
            return

        self.all_groups = groups
        self.groups_loaded = True
        for group_name in groups:
            self.group_listbox.insert(tk.END, group_name)

        selected = self._safe_load_selected_groups()
        for idx, name in enumerate(groups):
            if name in selected:
                self.group_listbox.selection_set(idx)

        self._update_group_counter()

    def _safe_load_selected_groups(self) -> list[str]:
        try:
            selected = config_manager.get_selected_groups()
            return selected if isinstance(selected, list) else []
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"恢复已选群失败：{exc}")
            return []

    def _on_group_selection_change(self, _event: tk.Event | None = None) -> None:
        self._update_group_counter()
        self._save_selected_groups()

    def _update_group_counter(self) -> None:
        total = len(self.all_groups)
        selected = len(self._get_selected_groups_from_ui()) if self.groups_loaded else 0
        self.group_count_var.set(f"共 {total} 个群 · 已选 {selected} 个")

    def _save_selected_groups(self) -> None:
        if not self.groups_loaded:
            return
        try:
            config_manager.save_selected_groups(self._get_selected_groups_from_ui())
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"保存群选择失败：{exc}")

    def _on_provider_change(self, save: bool = True) -> None:
        selected = self.provider_var.get()
        if selected == "Anthropic (Claude)":
            self.base_url_var.set("https://api.anthropic.com")
            self.base_url_entry.config(state="disabled")
        else:
            self.base_url_entry.config(state="normal")

        if save:
            self.save_ai_config(show_message=False)

    def _on_report_range_change(self) -> None:
        self._refresh_date_preview()
        try:
            config = config_manager.load_config()
            config["report_days"] = REPORT_DAYS_MAP[self.report_label_var.get()]
            config_manager.save_config(config)
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"保存时间范围失败：{exc}")

    def _refresh_date_preview(self) -> None:
        report_days = REPORT_DAYS_MAP.get(self.report_label_var.get(), 1)
        end = datetime.now().date()
        start = end if report_days == 1 else (end.fromordinal(end.toordinal() - (report_days - 1)))
        if start == end:
            self.date_preview_var.set(f"( {end.isoformat()} )")
        else:
            self.date_preview_var.set(f"( {start.isoformat()} ~ {end.isoformat()} )")

    def _on_api_key_paste(self, _event: tk.Event | None = None) -> None:
        self.ai_api_key_entry.config(show="")
        self.root.after(1200, lambda: self.ai_api_key_entry.config(show="*"))

    def save_ai_config(self, show_message: bool = True) -> None:
        payload = {
            "provider": PROVIDER_VALUE_MAP.get(self.provider_var.get(), "anthropic"),
            "base_url": self.base_url_var.get().strip(),
            "api_key": self.ai_api_key_var.get().strip(),
            "model": self.model_var.get().strip(),
        }
        try:
            config_manager.save_ai_config(payload)
            if show_message:
                messagebox.showinfo("提示", "AI 配置已保存")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", f"保存 AI 配置失败：{exc}")

    def save_telegram_config(self, show_message: bool = True) -> None:
        try:
            config = config_manager.load_config()
            config["telegram_bot_token"] = self.telegram_token_var.get().strip()
            config["telegram_chat_id"] = self.telegram_chat_id_var.get().strip()
            config_manager.save_config(config)
            if show_message:
                messagebox.showinfo("提示", "Telegram 配置已保存")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("错误", f"保存 Telegram 配置失败：{exc}")

    def test_ai_connection(self) -> None:
        self.ai_test_result_var.set("测试中...")

        def worker() -> None:
            try:
                result = sender.test_connection()  # 按需求调用
                if isinstance(result, tuple):
                    success, message = result
                    text = "✅ 连接成功" if success else f"❌ {message or '连接失败'}"
                else:
                    text = f"结果: {result}"
            except Exception as exc:  # noqa: BLE001
                text = f"❌ {exc}"

            self.root.after(0, lambda: self.ai_test_result_var.set(text))

        threading.Thread(target=worker, daemon=True).start()

    def test_telegram_connection(self) -> None:
        if _is_mock_mode():
            self.telegram_test_result_var.set("✅ Mock 模式：连接成功")
            return

        token = self.telegram_token_var.get().strip()
        chat_id = self.telegram_chat_id_var.get().strip()
        if not token or not chat_id:
            messagebox.showwarning("提示", "请先填写 Telegram Bot Token 和 Chat ID")
            return

        self.telegram_test_result_var.set("测试中...")

        def worker() -> None:
            success, message = sender.test_connection(token, chat_id)
            text = "✅ 连接成功" if success else f"❌ {message or '连接失败'}"
            self.root.after(0, lambda: self.telegram_test_result_var.set(text))

        threading.Thread(target=worker, daemon=True).start()

    def _get_selected_groups_from_ui(self) -> list[str]:
        indexes = self.group_listbox.curselection()
        return [self.group_listbox.get(index) for index in indexes]

    def generate_and_send(self) -> None:
        is_mock_mode = _is_mock_mode()
        selected_groups = self._get_selected_groups_from_ui()
        if not selected_groups:
            messagebox.showwarning("提示", "请先选择至少一个群")
            return

        ai_config = {
            "provider": PROVIDER_VALUE_MAP.get(self.provider_var.get(), ""),
            "base_url": self.base_url_var.get().strip(),
            "api_key": self.ai_api_key_var.get().strip(),
            "model": self.model_var.get().strip(),
        }
        missing_ai = [
            label
            for key, label in [
                ("provider", "Provider"),
                ("base_url", "Base URL"),
                ("api_key", "API Key"),
                ("model", "Model"),
            ]
            if not ai_config[key]
        ]
        if is_mock_mode:
            missing_ai = []
        if missing_ai:
            messagebox.showwarning("提示", f"AI 配置未填写：{', '.join(missing_ai)}")
            return

        token = self.telegram_token_var.get().strip()
        chat_id = self.telegram_chat_id_var.get().strip()
        missing_tg = []
        if not token:
            missing_tg.append("Bot Token")
        if not chat_id:
            missing_tg.append("Chat ID")
        if is_mock_mode:
            missing_tg = []
            token = token or "mock-token"
            chat_id = chat_id or "mock-chat-id"
        if missing_tg:
            messagebox.showwarning("提示", f"Telegram 配置未填写：{', '.join(missing_tg)}")
            return

        self.run_button.config(state="disabled", text="处理中...")

        def task() -> None:
            try:
                self._run_generation_task(selected_groups, ai_config, token, chat_id)
            finally:
                self.root.after(0, lambda: self.run_button.config(state="normal", text="🚀 生成并发送日报"))

        threading.Thread(target=task, daemon=True).start()

    def _run_generation_task(
        self,
        selected_groups: list[str],
        ai_config: dict,
        token: str,
        chat_id: str,
    ) -> None:
        log = self._append_log_threadsafe
        log("正在解密数据库...")

        report_days = REPORT_DAYS_MAP.get(self.report_label_var.get(), 1)
        start_time, end_time = config_manager.get_report_range(report_days)
        date_label = end_time.strftime("%Y-%m-%d")

        summaries: list[tuple[str, str]] = []
        total = len(selected_groups)
        for idx, group in enumerate(selected_groups, start=1):
            log(f"正在读取「{group}」消息（{idx}/{total}）...")
            messages = extractor.get_messages(group, start_time, end_time)
            log(f"正在生成「{group}」摘要...")
            summary_text = summarizer.summarize(group, messages, ai_config)
            summaries.append((group, summary_text))

        report = sender.build_report(date_label, summaries)
        log("正在发送 Telegram...")
        if sender.send_report(report, token, chat_id):
            log("✅ 发送成功！")
        else:
            log("❌ 发送失败")

    def _append_log_threadsafe(self, message: str) -> None:
        self.root.after(0, lambda: self._append_log(message))

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {message}\n"
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, line)
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def _save_all_config(self) -> None:
        try:
            config = config_manager.load_config()
            config["selected_groups"] = self._get_selected_groups_from_ui() if self.groups_loaded else []
            config["report_days"] = REPORT_DAYS_MAP.get(self.report_label_var.get(), 1)
            config["telegram_bot_token"] = self.telegram_token_var.get().strip()
            config["telegram_chat_id"] = self.telegram_chat_id_var.get().strip()
            config["ai"] = {
                "provider": PROVIDER_VALUE_MAP.get(self.provider_var.get(), "anthropic"),
                "base_url": self.base_url_var.get().strip(),
                "api_key": self.ai_api_key_var.get().strip(),
                "model": self.model_var.get().strip(),
            }
            config_manager.save_config(config)
        except Exception as exc:  # noqa: BLE001
            self._append_log(f"保存配置失败：{exc}")

    def on_close(self) -> None:
        self._save_all_config()
        self.root.destroy()


def _is_mock_mode() -> bool:
    value = (os.getenv(WECHAT_MOCK_ENV) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def main() -> None:
    root = tk.Tk()
    WechatDigestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

