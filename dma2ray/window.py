from __future__ import annotations
import platform
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango
from . import autostart, paths, sysproxy
from .core import CoreManager, CoreStatus, find_core
from .flags import flag_for
from .installer import (
    ASSETS_XRAY,
    SUPPORTED_ARCHS,
    asset_name,
    current_arch,
    install_core,
)
from .ping import tcp_ping
from .speedtest import SpeedResult, speed_test
from .state import LOG_LEVELS, MODES, Profile, Store
from .subscriptions import FetchResult, fetch_and_parse
from .sysproxy import SysProxyError
from .tray import TrayController
from .vless import VlessError, parse_vless

MODE_LABELS = (
    "Прокси (SOCKS5/HTTP)",
    "Системный прокси",
    "ВПН (TUN, нужен root)",
)

SCHEMES = {
    "system": Adw.ColorScheme.DEFAULT,
    "light": Adw.ColorScheme.FORCE_LIGHT,
    "dark": Adw.ColorScheme.FORCE_DARK,
}
SCHEME_KEYS = tuple(SCHEMES)
SCHEME_LABELS = ("Как в системе", "Светлая", "Тёмная")

CSS = b"""
@define-color accent_bg_color #2f6bd8;
@define-color accent_fg_color #ffffff;
@define-color accent_color #3a7be8;

switch:checked {
    background-color: #2f6bd8;
}
.latency-good { color: #26a269; }
.latency-ok { color: #e5a50a; }
.latency-bad { color: #c01c28; }
.latency-unknown { color: alpha(currentColor, 0.55); }
.error-text { color: #c01c28; }
.section-hint { color: alpha(currentColor, 0.65); }
.latency-pill {
    background-color: alpha(currentColor, 0.14);
    border-radius: 999px;
    padding: 2px 10px;
    font-size: 0.9em;
    font-weight: bold;
}
.flag-big { font-size: 26px; }
.home-status { font-size: 1.4em; font-weight: 800; }
.connect-big {
    min-width: 128px;
    min-height: 128px;
    border-radius: 64px;
    padding: 0;
    color: #ffffff;
    transition: background-color 400ms ease, box-shadow 400ms ease;
}
.connect-idle { background-color: #26a269; }
.connect-idle:hover { background-color: #2ec27e; }
.connect-busy { background-color: #62a0ea; }
.connect-active { background-color: #c01c28; }
.connect-active:hover { background-color: #e01c28; }
.server-card {
    background-color: alpha(currentColor, 0.07);
    border-radius: 18px;
    padding: 14px 16px;
    transition: background-color 300ms ease;
}
.server-card:hover { background-color: alpha(currentColor, 0.12); }
.main-headerbar,
.main-switcherbar {
    background-color: #14386e;
}
.main-switcherbar {
    min-height: 44px;
    padding-top: 6px;
    padding-bottom: 6px;
}
.main-switcherbar button {
    min-width: 140px;
    min-height: 40px;
    font-size: 1.1em;
}
.main-switcherbar button:checked {
    background-color: #2f6bd8;
}
dialog button.suggested-action {
    background-color: #2f6bd8;
    color: #ffffff;
}
dialog button.suggested-action:hover {
    background-color: #3a7be8;
}
.kernel-btn {
    min-width: 112px;
    min-height: 34px;
    border-radius: 999px;
    font-weight: 600;
}
.kernel-icon {
    background-color: alpha(currentColor, 0.08);
    border-radius: 12px;
    padding: 10px;
}
window,
window.background,
window.csd,
window.csd decoration {
    border-radius: 0;
    box-shadow: none;
}
dialog-host > dialog,
dialog.bottom-sheet,
dialog.floating {
    border-radius: 0;
}
"""
def _fmt_time(timestamp: float) -> str:
    if not timestamp:
        return "никогда"
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(timestamp))

def _latency_class(ms: int | None) -> str:
    if ms is None:
        return "latency-unknown"
    if ms <= 150:
        return "latency-good"
    if ms <= 400:
        return "latency-ok"
    return "latency-bad"

def _latency_text(ms: int | None) -> str:
    return "—" if ms is None else f"{ms} мс"

_LATENCY_CLASSES = ("latency-good", "latency-ok", "latency-bad", "latency-unknown")

class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, store: Store) -> None:
        super().__init__(
            application=app,
            title=paths.APP_TITLE,
            default_width=440,
            default_height=800,
        )
        self.app = app
        self.store = store
        self.latencies: dict[str, int | None] = {}
        self._parsed: dict[str, object] = {}
        self._profile_rows: list[Gtk.Widget] = []
        self._sub_rows: list[Gtk.Widget] = []
        self._latency_labels: dict[str, Gtk.Label] = {}
        self._updating_subs: set[str] = set()
        self._pending_quick_sub: str | None = None
        self._pending_pings = 0
        self._last_ping_all = 0.0
        self._auto_ping_scheduled = False
        self._speed_running = False
        self._sysproxy_applied = False
        self._ping_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="ping")
        self._fetch_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="sub")
        self._speed_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="speed")
        self._last_error_shown: str | None = None
        self._closing = False
        self._settings_reverting = False
        self._log_timeout: int | None = None
        self._log_dialog: Adw.Dialog | None = None
        self._core = CoreManager(store, self._core_status_from_thread)
        self._core_tabs: dict[str, Adw.ActionRow] = {}
        self._core_buttons: dict[str, Gtk.Button] = {}
        self._core_hints: dict[str, str] = {}
        self._tray = TrayController(
            on_show=lambda: GLib.idle_add(self._present_from_tray),
            on_toggle=lambda: GLib.idle_add(self._toggle_connection),
            on_quit=lambda: GLib.idle_add(self.app.quit),
        )
        self._apply_color_scheme()
        self._install_css()
        self._build_actions()
        self._build_ui()
        self._install_icon()
        self._refresh_all()
        self._update_status(self._core.status)
        if find_core(self.store) is None:
            self._toast("Xray-core не найден — скачайте его в «Настройки → Ядро»")
        self.connect("close-request", self._on_close_request)
        if self.store.settings.get("tray_enabled", True):
            self._try_start_tray(silent=True)
    def _apply_color_scheme(self) -> None:
        key = str(self.store.settings.get("color_scheme", "system"))
        Adw.StyleManager.get_default().set_color_scheme(
            SCHEMES.get(key, Adw.ColorScheme.DEFAULT)
            )
    def _settings_scheme(self, row: Adw.ComboRow, _param) -> None:
        index = int(row.get_selected())
        if 0 <= index < len(SCHEME_KEYS):
             self.store.set_setting("color_scheme", SCHEME_KEYS[index])
             self._apply_color_scheme()
    
    # ---------------------------------------------------------------- public
    @property
    def tray_active(self) -> bool:
        return self._tray.is_active

    @property
    def core(self) -> CoreManager:
        return self._core

    def import_uris(self, uris: list[str]) -> None:
        added = 0
        for uri in uris:
            try:
                parsed = parse_vless(uri)
            except VlessError as exc:
                self._toast(f"Не удалось импортировать: {exc}")
                continue
            profile = self.store.add_profile(parsed.name, uri)
            self.store.select_profile(profile.id)
            added += 1
        if added:
            self._refresh_all()
            self._toast(f"Добавлено профилей: {added}")

    def shutdown(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._sysproxy_applied:
            self._sysproxy_applied = False
            try:
                sysproxy.revert()
            except Exception:
                pass
        try:
            self._core.shutdown()
        finally:
            self._tray.stop()
            self._ping_pool.shutdown(wait=False, cancel_futures=True)
            self._fetch_pool.shutdown(wait=False, cancel_futures=True)
            self._speed_pool.shutdown(wait=False, cancel_futures=True)
            if self._log_timeout is not None:
                GLib.source_remove(self._log_timeout)
                self._log_timeout = None

    # -------------------------------------------------------------- lifecycle
    def _on_close_request(self, *_args) -> bool:
        if (
            self.store.settings.get("tray_enabled", True)
            and self.store.settings.get("close_to_tray", True)
            and self._tray.is_active
        ):
            self.set_visible(False)
            return True
        self.app.quit()
        return True

    def _present_from_tray(self) -> bool:
        self.set_visible(True)
        self.present()
        return False

    # ------------------------------------------------------------------- ui
    @staticmethod
    def _install_css() -> None:
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    @staticmethod
    def _install_icon() -> None:
        if not paths.ICON_FILE.exists():
            return
        display = Gdk.Display.get_default()
        if not display:
            return
        try:
            theme = Gtk.IconTheme.get_for_display(display)
            theme.add_search_path(str(paths.ICON_FILE.parent))
        except Exception:
            pass

    def _build_ui(self) -> None:
        self.toast_overlay = Adw.ToastOverlay()
        toolbar = Adw.ToolbarView()
        self.header = Adw.HeaderBar()
        self.header.add_css_class("main-headerbar")
        self.window_title = Adw.WindowTitle(title=paths.APP_TITLE, subtitle="Отключено")
        self.header.set_title_widget(self.window_title)
        self.header.set_show_start_title_buttons(False)
        self.header.set_show_end_title_buttons(False)
        menu = Gio.Menu()
        menu.append("Добавить профиль", "win.add-profile")
        menu.append("Добавить подписку", "win.add-subscription")
        menu.append("Обновить подписки", "win.update-subscriptions")
        menu.append("Проверить все задержки", "win.ping-all")
        menu.append("Тест скорости", "win.speed-test")
        menu.append("Настройки", "win.settings")
        menu.append("Журнал Xray", "win.show-log")
        menu.append("О программе", "win.about")
        menu.append("Ядра", "win.kernels")
        menu.append("Выход", "win.quit")
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_menu_model(menu)
        menu_button.set_tooltip_text("Меню")
        self.header.pack_end(menu_button)
        toolbar.add_top_bar(self.header)
        self.view_stack = Adw.ViewStack()
        self.view_stack.set_vexpand(True)
        # Плавное переключение между вкладками (по умолчанию выключено).
        self.view_stack.set_enable_transitions(True)
        self.view_stack.set_transition_duration(350)
        home = self._build_home_page()
        self.view_stack.add_titled(home, "home", "Главная")
        servers = self._build_servers_page()
        self.view_stack.add_titled(servers, "servers", "Серверы")
        settings = self._build_settings_page()
        self.view_stack.add_titled(settings, "settings", "Настройки")
        self.switcher_bar = Adw.ViewSwitcherBar()
        self.switcher_bar.set_stack(self.view_stack)
        self.switcher_bar.set_reveal(True)
        self.switcher_bar.add_css_class("main-switcherbar")
        self._strip_switcher_icons()
        self.view_stack.connect(
            "notify::visible-child", lambda *_: self._strip_switcher_icons()
        )
        toolbar.add_bottom_bar(self.switcher_bar)
        toolbar.set_content(self.view_stack)
        self.toast_overlay.set_child(toolbar)
        self.set_content(self.toast_overlay)

    def _strip_switcher_icons(self) -> None:
        """Во вкладках снизу — только текст, без пиктограмм."""
        stack: list[Gtk.Widget] = [self.switcher_bar]
        while stack:
            widget = stack.pop()
            if isinstance(widget, Gtk.Image):
                widget.set_visible(False)
                continue
            child = widget.get_first_child()
            while child is not None:
                stack.append(child)
                child = child.get_next_sibling()

    def _build_home_page(self) -> Gtk.Widget:
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        clamp = Adw.Clamp()
        clamp.set_maximum_size(540)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_start(18)
        box.set_margin_end(18)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        self.home_status = Gtk.Label(label="Отключено")
        self.home_status.add_css_class("home-status")
        self.home_status.set_halign(Gtk.Align.CENTER)
        box.append(self.home_status)
        self.home_detail = Gtk.Label(label="Выберите профиль")
        self.home_detail.add_css_class("section-hint")
        self.home_detail.set_halign(Gtk.Align.CENTER)
        self.home_detail.set_wrap(True)
        self.home_detail.set_max_width_chars(44)
        box.append(self.home_detail)
        self.big_icon = Gtk.Image.new_from_icon_name("network-vpn-symbolic")
        self.big_icon.set_pixel_size(48)
        self.big_button = Gtk.Button()
        self.big_button.set_child(self.big_icon)
        self.big_button.add_css_class("connect-big")
        self.big_button.add_css_class("connect-idle")
        self.big_button.set_halign(Gtk.Align.CENTER)
        self.big_button.set_tooltip_text("Подключить или отключить")
        self.big_button.connect("clicked", lambda *_: self._toggle_connection())
        box.append(self.big_button)
        self.server_card = Gtk.Button()
        self.server_card.add_css_class("flat")
        self.server_card.add_css_class("server-card")
        self.server_card.set_halign(Gtk.Align.FILL)
        self.server_card.set_tooltip_text("Открыть список серверов")
        self.server_card.connect(
            "clicked", lambda *_: self.view_stack.set_visible_child_name("servers")
        )
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.card_flag = Gtk.Label(label="🌐")
        self.card_flag.add_css_class("flag-big")
        card.append(self.card_flag)
        card_text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card_text.set_hexpand(True)
        self.card_name = Gtk.Label(label="Нет профиля", xalign=0.0)
        self.card_name.add_css_class("heading")
        self.card_name.set_ellipsize(Pango.EllipsizeMode.END)
        card_text.append(self.card_name)
        self.card_addr = Gtk.Label(label="Добавьте vless:// или подписку", xalign=0.0)
        self.card_addr.add_css_class("section-hint")
        self.card_addr.set_ellipsize(Pango.EllipsizeMode.END)
        card_text.append(self.card_addr)
        card.append(card_text)
        card_right = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        card_right.set_valign(Gtk.Align.CENTER)
        self.card_latency = Gtk.Label(label="")
        self._set_pill(self.card_latency, None, visible=False)
        card_right.append(self.card_latency)
        card_right.append(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        self.server_card.set_child(card)
        card.append(card_right)
        box.append(self.server_card)
        self.home_hint = Gtk.Label(
            label="Профилей пока нет. Вставьте ссылку vless:// или URL подписки ниже."
        )
        self.home_hint.set_wrap(True)
        self.home_hint.set_halign(Gtk.Align.CENTER)
        self.home_hint.add_css_class("section-hint")
        self.home_hint.set_visible(False)
        box.append(self.home_hint)
        self.quick_group = Adw.PreferencesGroup(
            title="Быстрое подключение",
            description="Вставьте ссылку vless:// или URL подписки — профиль добавится и подключится.",
        )
        self.quick_entry = Adw.EntryRow(title="vless://… или URL подписки")
        quick_button = Gtk.Button.new_from_icon_name("go-next-symbolic")
        quick_button.add_css_class("flat")
        quick_button.set_tooltip_text("Добавить и подключить")
        quick_button.connect("clicked", self._quick_connect)
        self.quick_entry.add_suffix(quick_button)
        self.quick_entry.connect("entry-activated", self._quick_connect)
        self.quick_group.add(self.quick_entry)
        box.append(self.quick_group)
        self.speed_group = Adw.PreferencesGroup(title="Скорость и задержка")
        speed_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.speed_button = Gtk.Button.new_from_icon_name("network-transmit-receive-symbolic")
        self.speed_button.add_css_class("flat")
        self.speed_button.set_tooltip_text("Измерить задержку и скорость через SOCKS5")
        self.speed_button.connect("clicked", lambda *_: self._run_speed_test())
        speed_actions.append(self.speed_button)
        self.speed_group.set_header_suffix(speed_actions)
        self.speed_latency_row = Adw.ActionRow(title="Задержка подключения", subtitle="—")
        self.speed_down_row = Adw.ActionRow(title="Скорость загрузки", subtitle="—")
        self.speed_group.add(self.speed_latency_row)
        self.speed_group.add(self.speed_down_row)
        box.append(self.speed_group)
        clamp.set_child(box)
        scrolled.set_child(clamp)
        return scrolled

    def _build_servers_page(self) -> Gtk.Widget:
        page = Adw.PreferencesPage()
        self.profiles_group = Adw.PreferencesGroup(title="Серверы")
        profile_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.sort_button = Gtk.Button.new_from_icon_name("view-list-symbolic")
        self.sort_button.add_css_class("flat")
        self.sort_button.set_tooltip_text("Сортировать по задержке")
        self.sort_button.connect("clicked", lambda *_: self._toggle_sort())
        profile_actions.append(self.sort_button)
        self.ping_all_button = Gtk.Button.new_from_icon_name(
            "network-cellular-signal-excellent-symbolic"
        )
        self.ping_all_button.add_css_class("flat")
        self.ping_all_button.set_tooltip_text("Проверить задержку всех серверов")
        self.ping_all_button.connect("clicked", lambda *_: self._ping_all())
        profile_actions.append(self.ping_all_button)
        add_profile_button = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_profile_button.add_css_class("flat")
        add_profile_button.set_tooltip_text("Добавить профиль")
        add_profile_button.connect("clicked", lambda *_: self._add_profile_dialog())
        profile_actions.append(add_profile_button)
        self.profiles_group.set_header_suffix(profile_actions)
        page.add(self.profiles_group)
        self.subs_group = Adw.PreferencesGroup(title="Подписки")
        sub_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        self.update_subs_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self.update_subs_button.add_css_class("flat")
        self.update_subs_button.set_tooltip_text("Обновить все подписки")
        self.update_subs_button.connect(
            "clicked", lambda *_: self._update_all_subscriptions()
        )
        sub_actions.append(self.update_subs_button)
        add_sub_button = Gtk.Button.new_from_icon_name("list-add-symbolic")
        add_sub_button.add_css_class("flat")
        add_sub_button.set_tooltip_text("Добавить подписку")
        add_sub_button.connect("clicked", lambda *_: self._add_subscription_dialog())
        sub_actions.append(add_sub_button)
        self.subs_group.set_header_suffix(sub_actions)
        page.add(self.subs_group)
        return page

    def _build_settings_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()
        connection = Adw.PreferencesGroup(
            title="Подключение",
            description="Изменения применятся при следующем подключении.",
        )
        mode_row = Adw.ComboRow(
            title="Режим подключения",
            subtitle="Локальный прокси · системный прокси ОС · ВПН через tun-интерфейс",
            model=Gtk.StringList.new(list(MODE_LABELS)),
        )
        mode_row.set_selected(MODES.index(self.store.mode))
        mode_row.connect("notify::selected", self._settings_mode)
        connection.add(mode_row)
        socks_row = Adw.SpinRow(
            title="SOCKS5-порт",
            subtitle="Локальный прокси для приложений",
            adjustment=Gtk.Adjustment(
                value=int(self.store.settings.get("socks_port", 10808)),
                lower=1,
                upper=65535,
                step_increment=1,
            ),
        )
        socks_row.set_digits(0)
        socks_row.connect("notify::value", lambda row, _p: self._settings_port("socks_port", row))
        connection.add(socks_row)
        http_row = Adw.SpinRow(
            title="HTTP-порт",
            subtitle="Локальный HTTP-прокси",
            adjustment=Gtk.Adjustment(
                value=int(self.store.settings.get("http_port", 10809)),
                lower=1,
                upper=65535,
                step_increment=1,
            ),
        )
        http_row.set_digits(0)
        http_row.connect("notify::value", lambda row, _p: self._settings_port("http_port", row))
        connection.add(http_row)
        log_row = Adw.ComboRow(title="Уровень журнала Xray")
        log_row.set_model(Gtk.StringList.new(list(LOG_LEVELS)))
        current_log = str(self.store.settings.get("log_level", "warning"))
        log_row.set_selected(LOG_LEVELS.index(current_log) if current_log in LOG_LEVELS else 2)
        log_row.connect("notify::selected", self._settings_log_level)
        connection.add(log_row)
        page.add(connection)
        appearance = Adw.PreferencesGroup(title="Оформление")
        scheme_row = Adw.ComboRow(
            title="Тема",
            subtitle="По умолчанию берётся из системы",
            model=Gtk.StringList.new(list(SCHEME_LABELS)),
        )
        current = str(self.store.settings.get("color_scheme", "system"))
        scheme_row.set_selected(
            SCHEME_KEYS.index(current) if current in SCHEME_KEYS else 0
        )
        scheme_row.connect("notify::selected", self._settings_scheme)
        appearance.add(scheme_row)
        page.add(appearance)
        interface = Adw.PreferencesGroup(title="Серверы и задержки")
        auto_ping_row = Adw.SwitchRow(
            title="Автопроверка задержки",
            subtitle="Пинговать серверы при обновлении списка",
        )
        auto_ping_row.set_active(bool(self.store.settings.get("auto_ping", True)))
        auto_ping_row.connect(
            "notify::active",
            lambda row, _p: self.store.set_setting("auto_ping", row.get_active()),
        )
        interface.add(auto_ping_row)
        sort_row = Adw.SwitchRow(
            title="Сортировать по задержке",
            subtitle="Сначала самые быстрые серверы",
        )
        sort_row.set_active(bool(self.store.settings.get("sort_by_latency", False)))
        sort_row.connect(
            "notify::active",
            lambda row, _p: self._settings_sort(row),
        )
        interface.add(sort_row)
        timeout_row = Adw.SpinRow(
            title="Таймаут проверки задержки",
            subtitle="Секунды на проверку одного сервера",
            adjustment=Gtk.Adjustment(
                value=float(self.store.settings.get("ping_timeout", 4.0)),
                lower=1.0,
                upper=30.0,
                step_increment=0.5,
            ),
        )
        timeout_row.set_digits(1)
        timeout_row.connect(
            "notify::value",
            lambda row, _p: self.store.set_setting("ping_timeout", float(row.get_value())),
        )
        interface.add(timeout_row)
        page.add(interface)
        startup = Adw.PreferencesGroup(title="Запуск и трей")
        autostart_row = Adw.SwitchRow(
            title="Автозапуск при входе",
            subtitle="Запускать Dma2ray вместе с сеансом",
        )
        autostart_row.set_active(autostart.is_enabled())
        autostart_row.connect("notify::active", self._settings_autostart)
        startup.add(autostart_row)
        tray_row = Adw.SwitchRow(
            title="Иконка в системном трее",
            subtitle="Отдельный GTK3-хелпер, совместимый с XFCE/GNOME/KDE",
        )
        tray_row.set_active(bool(self.store.settings.get("tray_enabled", True)))
        tray_row.connect("notify::active", self._settings_tray)
        startup.add(tray_row)
        close_row = Adw.SwitchRow(
            title="Закрывать окно в трей",
            subtitle="Приложение продолжит работать в фоне",
        )
        close_row.set_active(bool(self.store.settings.get("close_to_tray", True)))
        close_row.connect(
            "notify::active",
            lambda row, _p: self.store.set_setting("close_to_tray", row.get_active()),
        )
        startup.add(close_row)
        auto_row = Adw.SwitchRow(title="Подключаться при запуске")
        auto_row.set_active(bool(self.store.settings.get("auto_connect", False)))
        auto_row.connect(
            "notify::active",
            lambda row, _p: self.store.set_setting("auto_connect", row.get_active()),
        )
        startup.add(auto_row)
        page.add(startup)
        diagnostics = Adw.PreferencesGroup(title="Диагностика")
        log_action = Adw.ActionRow(title="Журнал Xray", subtitle="Последние сообщения ядра")
        log_action.set_activatable(True)
        log_action.connect("activated", lambda *_: self._show_log())
        diagnostics.add(log_action)
        data_action = Adw.ActionRow(
            title="Каталог данных",
            subtitle=str(paths.DATA_DIR),
        )
        data_action.set_activatable(True)
        data_action.connect("activated", self._open_data_dir)
        diagnostics.add(data_action)
        page.add(diagnostics)
        return page

    # --------------------------------------------------------------- actions
    def _build_actions(self) -> None:
        simple = {
            "add-profile": lambda *_: self._add_profile_dialog(),
            "add-subscription": lambda *_: self._add_subscription_dialog(),
            "update-subscriptions": lambda *_: self._update_all_subscriptions(),
            "ping-all": lambda *_: self._ping_all(),
            "speed-test": lambda *_: self._run_speed_test(),
            "settings": lambda *_: self.view_stack.set_visible_child_name("settings"),
            "show-log": lambda *_: self._show_log(),
            "about": lambda *_: self._about_dialog(),
            "kernels": lambda *_: self._show_kernels_dialog(),
            "quit": lambda *_: self.app.quit(),
        }
        for name, callback in simple.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)
        string_actions = {
            "ping": self._ping_action,
            "rename": self._rename_action,
            "remove-profile": self._remove_profile_action,
            "connect": self._connect_action,
            "update-sub": self._update_sub_action,
            "remove-sub": self._remove_sub_action,
        }
        for name, callback in string_actions.items():
            action = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            action.connect("activate", callback)
            self.add_action(action)

    def _ping_action(self, _action, parameter) -> None:
        self._ping_profile(parameter.get_string())

    def _rename_action(self, _action, parameter) -> None:
        self._rename_dialog(parameter.get_string())

    def _remove_profile_action(self, _action, parameter) -> None:
        self._remove_profile_dialog(parameter.get_string())

    def _connect_action(self, _action, parameter) -> None:
        profile_id = parameter.get_string()
        if not self.store.get_profile(profile_id):
            return
        self.store.select_profile(profile_id)
        self._refresh_all()
        self._start_selected()

    def _update_sub_action(self, _action, parameter) -> None:
        self._update_subscription(parameter.get_string())

    def _remove_sub_action(self, _action, parameter) -> None:
        self._remove_subscription_dialog(parameter.get_string())

    # --------------------------------------------------------------- refresh
    def _refresh_all(self) -> None:
        self._rebuild_profiles()
        self._rebuild_subscriptions()
        has_content = bool(self.store.profiles or self.store.subscriptions)
        self.home_hint.set_visible(not has_content)
        self._update_status(self._core.status)
        self._maybe_auto_ping()

    def _clear_rows(self, group: Adw.PreferencesGroup, rows: list[Gtk.Widget]) -> None:
        for row in rows:
            try:
                group.remove(row)
            except Exception:
                pass
        rows.clear()

    def _sorted_profiles(self) -> list[Profile]:
        profiles = list(self.store.profiles)
        if self.store.settings.get("sort_by_latency"):
            profiles.sort(
                key=lambda item: (
                    self.latencies.get(item.id) is None,
                    self.latencies.get(item.id) or 0,
                )
            )
        return profiles

    def _rebuild_profiles(self) -> None:
        self._clear_rows(self.profiles_group, self._profile_rows)
        self._latency_labels.clear()
        self.sort_button.set_tooltip_text(
            "Сортировка: по задержке (выкл.)"
            if not self.store.settings.get("sort_by_latency")
            else "Сортировка: по задержке (вкл.)"
        )
        if not self.store.profiles:
            row = Adw.ActionRow(
                title="Профилей пока нет",
                subtitle="Вставьте ссылку vless:// или добавьте подписку",
            )
            self.profiles_group.add(row)
            self._profile_rows.append(row)
            return
        selected_id = self.store.settings.get("selected_profile_id")
        for profile in self._sorted_profiles():
            parsed = self._profile_parsed(profile)
            subtitle = parsed.detail() if parsed else "Некорректная ссылка vless://"
            row = Adw.ActionRow(title=profile.name, subtitle=subtitle)
            row.set_activatable(True)
            row.connect(
                "activated", lambda *_args, pid=profile.id: self._select_profile(pid)
            )
            check = Gtk.Image.new_from_icon_name("object-select-symbolic")
            check.set_visible(profile.id == selected_id)
            row.add_prefix(check)
            flag = flag_for(profile.name, parsed.address if parsed else "")
            if flag:
                flag_label = Gtk.Label(label=flag)
                flag_label.set_margin_start(6)
                row.add_prefix(flag_label)
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            box.set_valign(Gtk.Align.CENTER)
            latency = Gtk.Label(label=_latency_text(self.latencies.get(profile.id)))
            self._set_pill(latency, self.latencies.get(profile.id))
            box.append(latency)
            self._latency_labels[profile.id] = latency
            menu = Gio.Menu()
            for label, action in (
                ("Подключить", "win.connect"),
                ("Проверить задержку", "win.ping"),
                ("Переименовать", "win.rename"),
                ("Удалить", "win.remove-profile"),
            ):
                item = Gio.MenuItem.new(label, None)
                item.set_action_and_target_value(action, GLib.Variant("s", profile.id))
                menu.append_item(item)
            menu_button = Gtk.MenuButton()
            menu_button.set_icon_name("view-more-symbolic")
            menu_button.set_menu_model(menu)
            menu_button.add_css_class("flat")
            menu_button.set_tooltip_text("Действия с профилем")
            box.append(menu_button)
            row.add_suffix(box)
            self.profiles_group.add(row)
            self._profile_rows.append(row)

    def _rebuild_subscriptions(self) -> None:
        self._clear_rows(self.subs_group, self._sub_rows)
        if not self.store.subscriptions:
            row = Adw.ActionRow(
                title="Подписок пока нет",
                subtitle="Добавьте URL подписки, чтобы получать профили автоматически",
            )
            self.subs_group.add(row)
            self._sub_rows.append(row)
            return
        for sub in self.store.subscriptions:
            count = len(self.store.profiles_for_subscription(sub.id))
            if sub.id in self._updating_subs:
                subtitle = "Обновление…"
            elif sub.last_error:
                subtitle = f"{count} профилей · {sub.last_error}"
            else:
                subtitle = f"{count} профилей · обновлено {_fmt_time(sub.updated_at)}"
            row = Adw.ActionRow(title=sub.name, subtitle=subtitle)
            row.set_subtitle_lines(2)
            icon = Gtk.Image.new_from_icon_name("view-refresh-symbolic")
            row.add_prefix(icon)
            if sub.id in self._updating_subs:
                spinner = Gtk.Spinner()
                spinner.start()
                row.add_suffix(spinner)
            menu = Gio.Menu()
            update_item = Gio.MenuItem.new("Обновить", None)
            update_item.set_action_and_target_value(
                "win.update-sub", GLib.Variant("s", sub.id)
            )
            menu.append_item(update_item)
            delete_item = Gio.MenuItem.new("Удалить подписку", None)
            delete_item.set_action_and_target_value(
                "win.remove-sub", GLib.Variant("s", sub.id)
            )
            menu.append_item(delete_item)
            menu_button = Gtk.MenuButton()
            menu_button.set_icon_name("view-more-symbolic")
            menu_button.set_menu_model(menu)
            menu_button.add_css_class("flat")
            row.add_suffix(menu_button)
            self.subs_group.add(row)
            self._sub_rows.append(row)

    def _profile_parsed(self, profile: Profile):
        if profile.uri not in self._parsed:
            try:
                self._parsed[profile.uri] = parse_vless(profile.uri)
            except VlessError:
                self._parsed[profile.uri] = None
        return self._parsed[profile.uri]

    # ---------------------------------------------------------------- status
    def _core_status_from_thread(self, status: CoreStatus) -> None:
        GLib.idle_add(self._apply_core_status, status)

    def _apply_core_status(self, status: CoreStatus) -> bool:
        self._update_status(status)
        if status.state == "error" and status.error and status.error != self._last_error_shown:
            self._last_error_shown = status.error
            self._toast(f"Ошибка: {status.error.splitlines()[0]}")
        return False

    def _update_status(self, status: CoreStatus) -> None:
        selected = self.store.selected_profile
        mode = self._mode_text()
        state = status.state
        if state == "running":
            profile = self.store.get_profile(status.profile_id) or selected
            subtitle = f"{profile.name} · {mode}" if profile else mode
            self.window_title.set_subtitle("Подключено")
            self._set_connect_button(
                "Отключиться", "media-playback-stop-symbolic", destructive=True
            )
            self.home_status.set_text("Подключено")
            self.home_detail.set_text(subtitle)
        elif state == "starting":
            subtitle = status.detail or "Запуск Xray…"
            self.window_title.set_subtitle("Подключение…")
            self._set_connect_button(
                "Подключение…", "network-transmit-receive-symbolic", sensitive=False
            )
            self.home_status.set_text("Подключение…")
            self.home_detail.set_text(subtitle)
        elif state == "error":
            first = (status.error or "Неизвестная ошибка").splitlines()[0]
            self.window_title.set_subtitle("Ошибка")
            self._set_connect_button("Повторить", "network-vpn-symbolic")
            self.home_status.set_text("Ошибка")
            self.home_detail.set_text(first)
        else:
            if selected:
                parsed = self._profile_parsed(selected)
                subtitle = parsed.detail() if parsed else "Некорректная ссылка"
            else:
                subtitle = "Выберите профиль или добавьте новый"
            self.window_title.set_subtitle("Отключено")
            self._set_connect_button("Подключиться", "network-vpn-symbolic")
            self.home_status.set_text("Отключено")
            self.home_detail.set_text(subtitle)
        self._update_server_card(status)
        profile_name = ""
        if state in ("running", "starting", "error") and status.profile_id:
            profile = self.store.get_profile(status.profile_id)
            profile_name = profile.name if profile else ""
        self._tray.send_state(
            "running"
            if state == "running"
            else ("starting" if state == "starting" else "stopped"),
            profile_name,
        )
        self._sync_sysproxy(status)

    def _update_server_card(self, status: CoreStatus | None = None) -> None:
        status = status or self._core.status
        profile: Profile | None = None
        if status.state in ("running", "starting", "error") and status.profile_id:
            profile = self.store.get_profile(status.profile_id)
        profile = profile or self.store.selected_profile
        if not profile:
            self.card_flag.set_text("🌐")
            self.card_name.set_text("Нет профиля")
            self.card_addr.set_text("Добавьте vless:// или подписку")
            self._set_pill(self.card_latency, None, visible=False)
            return
        parsed = self._profile_parsed(profile)
        flag = flag_for(profile.name, parsed.address if parsed else "")
        self.card_flag.set_text(flag or "🌐")
        self.card_name.set_text(profile.name)
        self.card_addr.set_text(
            f"{parsed.address}:{parsed.port}" if parsed else "Некорректная ссылка"
        )
        self._set_pill(self.card_latency, self.latencies.get(profile.id))

    @staticmethod
    def _set_pill(label: Gtk.Label, ms: int | None, *, visible: bool = True) -> None:
        for css in ("latency-pill", *_LATENCY_CLASSES):
            label.remove_css_class(css)
        if not visible:
            label.set_text("")
            label.set_visible(False)
            return
        label.set_visible(True)
        label.add_css_class("latency-pill")
        label.add_css_class(_latency_class(ms))
        label.set_text(_latency_text(ms))

    def _set_connect_button(
        self,
        label: str,
        icon: str,
        *,
        sensitive: bool = True,
        destructive: bool = False,
    ) -> None:
        self.big_icon.set_from_icon_name(icon)
        self.big_button.set_sensitive(sensitive)
        for css in ("connect-idle", "connect-busy", "connect-active"):
            self.big_button.remove_css_class(css)
        if destructive:
            self.big_button.add_css_class("connect-active")
        elif not sensitive:
            self.big_button.add_css_class("connect-busy")
        else:
            self.big_button.add_css_class("connect-idle")
        self.big_button.set_tooltip_text(label)

    def _mode_text(self) -> str:
        socks = self.store.settings.get("socks_port", 10808)
        http = self.store.settings.get("http_port", 10809)
        mode = self.store.mode
        if mode == "vpn":
            return f"ВПН (TUN) + SOCKS 127.0.0.1:{socks}"
        if mode == "system":
            return f"Системный прокси · HTTP 127.0.0.1:{http}"
        return f"SOCKS 127.0.0.1:{socks} · HTTP 127.0.0.1:{http}"

    # ----------------------------------------------------------- sys proxy
    def _sync_sysproxy(self, status: CoreStatus) -> None:
        want = status.state == "running" and self.store.mode == "system"
        if want and not self._sysproxy_applied:
            self._sysproxy_applied = True
            http_port = int(self.store.settings.get("http_port", 10809))
            socks_port = int(self.store.settings.get("socks_port", 10808))
            def worker() -> None:
                try:
                    sysproxy.apply(http_port, socks_port)
                except SysProxyError as exc:
                    GLib.idle_add(self._sysproxy_failed, str(exc))
                else:
                    GLib.idle_add(self._toast, "Системный прокси включён")
            try:
                self._fetch_pool.submit(worker)
            except RuntimeError:
                self._sysproxy_applied = False
        elif not want and self._sysproxy_applied:
            self._sysproxy_applied = False
            try:
                self._fetch_pool.submit(self._revert_sysproxy_quiet)
            except RuntimeError:
                pass

    @staticmethod
    def _revert_sysproxy_quiet() -> None:
        try:
            sysproxy.revert()
        except Exception:
            pass

    def _sysproxy_failed(self, message: str) -> bool:
        self._sysproxy_applied = False
        self._toast(f"Системный прокси не включён: {message}")
        return False

    # ------------------------------------------------------------- connecting
    def _toggle_connection(self) -> None:
        status = self._core.status
        if status.state in ("running", "starting"):
            self._core.stop()
            return
        self._start_selected()

    def _start_selected(self) -> None:
        profile = self.store.selected_profile
        if not profile:
            self._toast("Сначала добавьте и выберите профиль")
            return
        try:
            parse_vless(profile.uri)
        except VlessError as exc:
            self._toast(f"Профиль некорректен: {exc}")
            return
        tun = self.store.mode == "vpn"
        self._core.start(profile, tun)

    def _select_profile(self, profile_id: str) -> None:
        self.store.select_profile(profile_id)
        self._refresh_all()
        profile = self.store.get_profile(profile_id)
        if profile:
            self._toast(f"Выбран профиль: {profile.name}")
        # При смене сервера в режиме ВПН (TUN) переподключаемся автоматически.
        status = self._core.status
        if status.state == "running" and self.store.mode == "vpn":
            self._start_selected()

    # ----------------------------------------------------------- quick connect
    def _quick_connect(self, *_args) -> None:
        text = self.quick_entry.get_text().strip()
        if not text:
            self._toast("Вставьте ссылку vless:// или URL подписки")
            return
        lowered = text.lower()
        if lowered.startswith("vless://"):
            try:
                parsed = parse_vless(text)
            except VlessError as exc:
                self._toast(f"Некорректная ссылка: {exc}")
                return
            profile = self.store.add_profile(parsed.name, text)
            self.store.select_profile(profile.id)
            self.quick_entry.set_text("")
            self._refresh_all()
            self._toast(f"Профиль «{profile.name}» добавлен")
            self._start_selected()
        elif lowered.startswith(("http://", "https://")):
            sub = self.store.add_subscription(text, text)
            self.quick_entry.set_text("")
            self._pending_quick_sub = sub.id
            self._refresh_all()
            self._toast("Подписка добавлена, загружаю профили…")
            self._update_subscription(sub.id)
        else:
            self._toast("Нужна ссылка vless:// или URL подписки (http/https)")

    # ------------------------------------------------------------------- ping
    def _ping_profile(self, profile_id: str) -> None:
        profile = self.store.get_profile(profile_id)
        if not profile:
            return
        parsed = self._profile_parsed(profile)
        if parsed is None:
            return
        label = self._latency_labels.get(profile_id)
        if label:
            label.set_text("…")
        timeout = float(self.store.settings.get("ping_timeout", 4.0))
        try:
            future = self._ping_pool.submit(tcp_ping, parsed.address, parsed.port, timeout)
        except RuntimeError:
            return
        self._pending_pings += 1
        future.add_done_callback(
            lambda f, pid=profile_id: GLib.idle_add(self._finish_ping, pid, f)
        )

    def _finish_ping(self, profile_id: str, future) -> bool:
        try:
            ms = future.result()
        except Exception:
            ms = None
        self.latencies[profile_id] = ms
        label = self._latency_labels.get(profile_id)
        if label:
            self._set_pill(label, ms)
        self._pending_pings = max(0, self._pending_pings - 1)
        self._update_server_card()
        if self._pending_pings == 0 and self.store.settings.get("sort_by_latency"):
            self._rebuild_profiles()
        return False

    def _ping_all(self) -> None:
        if not self.store.profiles:
            self._toast("Нет профилей для проверки")
            return
        self._last_ping_all = time.time()
        for profile in self.store.profiles:
            self._ping_profile(profile.id)

    def _maybe_auto_ping(self) -> None:
        if not self.store.settings.get("auto_ping", True):
            return
        if not self.store.profiles:
            return
        if time.time() - self._last_ping_all < 20:
            return
        if self._auto_ping_scheduled:
            return
        self._auto_ping_scheduled = True
        GLib.timeout_add(400, self._auto_ping_tick)

    def _auto_ping_tick(self) -> bool:
        self._auto_ping_scheduled = False
        if not self._closing:
            self._ping_all()
        return False

    def _toggle_sort(self) -> None:
        current = bool(self.store.settings.get("sort_by_latency"))
        self.store.set_setting("sort_by_latency", not current)
        self._rebuild_profiles()
        self._toast("Сортировка по задержке включена" if not current else "Сортировка отключена")

    # ------------------------------------------------------------- speed test
    def _run_speed_test(self, *_args) -> None:
        if not self._core.is_running:
            self._toast("Сначала подключитесь — тест идёт через локальный SOCKS5")
            return
        if self._speed_running:
            return
        self._speed_running = True
        self.speed_button.set_sensitive(False)
        self.speed_latency_row.set_subtitle("Измерение…")
        self.speed_down_row.set_subtitle("Измерение…")
        socks_port = int(self.store.settings.get("socks_port", 10808))
        def worker() -> None:
            try:
                result = speed_test("127.0.0.1", socks_port)
            except Exception as exc:  # pragma: no cover - defensive
                result = SpeedResult(error=str(exc) or exc.__class__.__name__)
            GLib.idle_add(self._finish_speed_test, result)
        self._speed_pool.submit(worker)

    def _finish_speed_test(self, result: SpeedResult) -> bool:
        self._speed_running = False
        self.speed_button.set_sensitive(True)
        if result.error:
            self.speed_latency_row.set_subtitle(
                _latency_text(result.latency_ms) if result.latency_ms else "—"
            )
            self.speed_down_row.set_subtitle(result.error)
            return False
        self.speed_latency_row.set_subtitle(_latency_text(result.latency_ms))
        self.speed_down_row.set_subtitle(f"{result.mbps} Мбит/с")
        return False

    # ----------------------------------------------------------- subscriptions
    def _add_subscription_dialog(self) -> None:
        dialog = Adw.Dialog()
        dialog.set_title("Новая подписка")
        dialog.set_content_width(480)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(title="Новая подписка", subtitle="URL со списком vless://")
        )
        cancel = Gtk.Button(label="Отмена")
        cancel.connect("clicked", lambda *_: dialog.close())
        header.pack_start(cancel)
        add = Gtk.Button(label="Добавить")
        add.add_css_class("suggested-action")
        add.set_sensitive(False)
        header.pack_end(add)
        toolbar.add_top_bar(header)
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup()
        name_row = Adw.EntryRow(title="Название")
        url_row = Adw.EntryRow(title="URL подписки")
        group.add(name_row)
        group.add(url_row)
        page.add(group)
        toolbar.set_content(page)
        dialog.set_child(toolbar)
        def update_sensitive(*_args) -> None:
            add.set_sensitive(
                url_row.get_text().strip().startswith(("http://", "https://"))
            )
        url_row.connect("changed", update_sensitive)
        def on_add(*_args) -> None:
            url = url_row.get_text().strip()
            if not url.startswith(("http://", "https://")):
                self._toast("URL должен начинаться с http:// или https://")
                return
            name = name_row.get_text().strip() or url
            sub = self.store.add_subscription(name, url)
            dialog.close()
            self._refresh_all()
            self._toast("Подписка добавлена, загружаю профили…")
            self._update_subscription(sub.id)
        add.connect("clicked", on_add)
        url_row.connect("entry-activated", lambda *_: on_add())
        dialog.present(self)

    def _update_all_subscriptions(self) -> None:
        if not self.store.subscriptions:
            self._toast("Подписок пока нет")
            return
        for sub in list(self.store.subscriptions):
            self._update_subscription(sub.id)

    def _update_subscription(self, sub_id: str) -> None:
        sub = self.store.get_subscription(sub_id)
        if not sub:
            return
        if sub_id in self._updating_subs:
            self._toast("Эта подписка уже обновляется")
            return
        self._updating_subs.add(sub_id)
        self._rebuild_subscriptions()
        future = self._fetch_pool.submit(fetch_and_parse, sub.url, 25.0)
        future.add_done_callback(
            lambda f, sid=sub_id: GLib.idle_add(self._finish_subscription, sid, f)
        )

    def _finish_subscription(self, sub_id: str, future) -> bool:
        self._updating_subs.discard(sub_id)
        sub = self.store.get_subscription(sub_id)
        if sub is None:
            self._pending_quick_sub = (
                None if self._pending_quick_sub == sub_id else self._pending_quick_sub
            )
            self._rebuild_subscriptions()
            return False
        try:
            result: FetchResult = future.result()
        except Exception as exc:
            if self._pending_quick_sub == sub_id:
                self._pending_quick_sub = None
            message = str(exc) or exc.__class__.__name__
            self.store.set_subscription_error(sub_id, message)
            self._toast(f"Ошибка подписки «{sub.name}»: {message}")
            self._rebuild_subscriptions()
            return False
        if not result.entries:
            if self._pending_quick_sub == sub_id:
                self._pending_quick_sub = None
            if result.unsupported:
                message = f"Нет VLESS-ссылок (пропущено {result.unsupported} других)"
            elif result.invalid:
                message = f"Нет валидных VLESS-ссылок (ошибок: {result.invalid})"
            else:
                message = "В подписке не найдено ссылок"
            self.store.set_subscription_error(sub_id, message)
            self._toast(f"Подписка «{sub.name}»: {message}")
            self._rebuild_subscriptions()
            return False
        count = self.store.replace_subscription_profiles(sub_id, result.entries)
        details = f"Обновлено: {count} профилей"
        if result.unsupported:
            details += f", пропущено {result.unsupported}"
        self._toast(f"«{sub.name}»: {details}")
        if self._pending_quick_sub == sub_id:
            self._pending_quick_sub = None
            profiles = self.store.profiles_for_subscription(sub_id)
            if profiles:
                self.store.select_profile(profiles[0].id)
                self._refresh_all()
                self._start_selected()
                return False
        self._refresh_all()
        return False

    def _remove_subscription_dialog(self, sub_id: str) -> None:
        sub = self.store.get_subscription(sub_id)
        if not sub:
            return
        dialog = Adw.AlertDialog(
            heading="Удалить подписку?",
            body=f"«{sub.name}» и все её профили будут удалены.",
        )
        dialog.add_response("cancel", "Отмена")
        dialog.add_response("delete", "Удалить")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        def on_response(dialog_obj, result) -> None:
            try:
                response = dialog_obj.choose_finish(result)
            except GLib.Error:
                return
            if response != "delete":
                return
            active = self.store.get_profile(self._core.status.profile_id)
            active_sub = active.subscription_id if active else None
            self.store.remove_subscription(sub_id)
            self._refresh_all()
            if active_sub == sub_id or not self.store.profiles:
                self._core.stop()
            self._toast("Подписка удалена")
        dialog.choose(self, None, on_response)

    # ---------------------------------------------------------------- profiles
    def _add_profile_dialog(self) -> None:
        dialog = Adw.Dialog()
        dialog.set_title("Новый профиль")
        dialog.set_content_width(480)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(title="Новый профиль", subtitle="Импорт vless://")
        )
        cancel = Gtk.Button(label="Отмена")
        cancel.connect("clicked", lambda *_: dialog.close())
        header.pack_start(cancel)
        add = Gtk.Button(label="Добавить")
        add.add_css_class("suggested-action")
        add.set_sensitive(False)
        header.pack_end(add)
        toolbar.add_top_bar(header)
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title="Ссылка",
            description="Вставьте ссылку vless://, выданную сервером или панелью.",
        )
        link_row = Adw.EntryRow(title="vless://…")
        paste = Gtk.Button.new_from_icon_name("edit-paste-symbolic")
        paste.add_css_class("flat")
        paste.set_tooltip_text("Вставить из буфера обмена")
        link_row.add_suffix(paste)
        group.add(link_row)
        name_row = Adw.EntryRow(title="Название (необязательно)")
        group.add(name_row)
        preview_row = Adw.ActionRow(title="Предпросмотр", subtitle="—")
        preview_row.set_subtitle_lines(2)
        group.add(preview_row)
        error_label = Gtk.Label(label="")
        error_label.set_wrap(True)
        error_label.set_xalign(0.0)
        error_label.add_css_class("error-text")
        error_label.set_margin_start(12)
        error_label.set_margin_end(12)
        error_label.set_margin_top(6)
        error_label.set_visible(False)
        group.add(error_label)
        page.add(group)
        toolbar.set_content(page)
        dialog.set_child(toolbar)
        parsed_holder: dict[str, object] = {}
        def update(*_args) -> None:
            uri = link_row.get_text().strip()
            error_label.set_visible(False)
            parsed_holder.clear()
            if not uri:
                preview_row.set_subtitle("—")
                add.set_sensitive(False)
                return
            try:
                parsed = parse_vless(uri)
            except VlessError as exc:
                preview_row.set_subtitle("Некорректная ссылка")
                error_label.set_text(str(exc))
                error_label.set_visible(True)
                add.set_sensitive(False)
                return
            parsed_holder["profile"] = parsed
            preview_row.set_subtitle(parsed.detail())
            add.set_sensitive(True)
        link_row.connect("changed", update)
        def on_paste(*_args) -> None:
            display = Gdk.Display.get_default()
            if not display:
                return
            clipboard = display.get_clipboard()
            def on_text(_clipboard, result) -> None:
                try:
                    text = clipboard.read_text_finish(result)
                except GLib.Error:
                    return
                if text:
                    link_row.set_text(text.strip().splitlines()[0])
            clipboard.read_text_async(None, on_text)
        paste.connect("clicked", on_paste)
        def on_add(*_args) -> None:
            parsed = parsed_holder.get("profile")
            if parsed is None:
                update()
                parsed = parsed_holder.get("profile")
            if parsed is None:
                return
            name = name_row.get_text().strip() or parsed.name
            profile = self.store.add_profile(name, link_row.get_text().strip())
            self.store.select_profile(profile.id)
            dialog.close()
            self._refresh_all()
            self._toast(f"Профиль «{profile.name}» добавлен")
        add.connect("clicked", on_add)
        link_row.connect("entry-activated", lambda *_: on_add())
        dialog.present(self)

    def _rename_dialog(self, profile_id: str) -> None:
        profile = self.store.get_profile(profile_id)
        if not profile:
            return
        dialog = Adw.AlertDialog(
            heading="Переименовать профиль", body="Введите новое название."
        )
        entry = Gtk.Entry()
        entry.set_text(profile.name)
        entry.set_activates_default(True)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Отмена")
        dialog.add_response("save", "Сохранить")
        dialog.set_default_response("save")
        dialog.set_close_response("cancel")
        def on_response(dialog_obj, result) -> None:
            try:
                response = dialog_obj.choose_finish(result)
            except GLib.Error:
                return
            if response != "save":
                return
            self.store.rename_profile(profile_id, entry.get_text())
            self._refresh_all()
        dialog.choose(self, None, on_response)

    def _remove_profile_dialog(self, profile_id: str) -> None:
        profile = self.store.get_profile(profile_id)
        if not profile:
            return
        dialog = Adw.AlertDialog(
            heading="Удалить профиль?",
            body=f"«{profile.name}» будет удалён.",
        )
        dialog.add_response("cancel", "Отмена")
        dialog.add_response("delete", "Удалить")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_close_response("cancel")
        def on_response(dialog_obj, result) -> None:
            try:
                response = dialog_obj.choose_finish(result)
            except GLib.Error:
                return
            if response != "delete":
                return
            active = self._core.status.profile_id
            self.store.remove_profile(profile_id)
            if active == profile_id:
                self._core.stop()
            self._refresh_all()
            self._toast("Профиль удалён")
        dialog.choose(self, None, on_response)

    # ---------------------------------------------------------------- settings
    def _settings_mode(self, row: Adw.ComboRow, _param) -> None:
        index = int(row.get_selected())
        if not 0 <= index < len(MODES):
            return
        mode = MODES[index]
        if mode == self.store.mode:
            return
        self.store.set_mode(mode)
        self._update_status(self._core.status)
        self._sync_sysproxy(self._core.status)
        notes = {
            "vpn": "Режим «ВПН»: при подключении потребуется пароль root (pkexec).",
            "system": (
                "Режим «Системный прокси»: настройки прокси ОС будут изменены "
                "при подключении и восстановлены при отключении."
            ),
            "proxy": (
                "Режим «Прокси»: локальные SOCKS5/HTTP, "
                "приложения настраиваются вручную."
            ),
        }
        message = notes[mode]
        if self._core.is_running:
            message += " Переподключитесь, чтобы применить."
        self._toast(message)

    def _settings_sort(self, row: Adw.SwitchRow) -> None:
        self.store.set_setting("sort_by_latency", bool(row.get_active()))
        self._rebuild_profiles()

    def _settings_port(self, key: str, row: Adw.SpinRow) -> None:
        value = int(row.get_value())
        if self.store.settings.get(key) == value:
            return
        other = "http_port" if key == "socks_port" else "socks_port"
        if value == int(self.store.settings.get(other, 0)):
            self._toast("Порты SOCKS и HTTP должны различаться")
            old = int(self.store.settings.get(key, value))
            if int(row.get_value()) != old:
                row.set_value(old)
            return
        self.store.set_setting(key, value)
        self._update_status(self._core.status)
        if self._core.is_running:
            self._toast("Переподключитесь, чтобы применить порт")

    def _settings_log_level(self, row: Adw.ComboRow, _param) -> None:
        index = int(row.get_selected())
        if 0 <= index < len(LOG_LEVELS):
            self.store.set_setting("log_level", LOG_LEVELS[index])

    def _settings_autostart(self, row: Adw.SwitchRow, _param=None) -> None:
        if self._settings_reverting:
            return
        enabled = bool(row.get_active())
        try:
            autostart.set_enabled(enabled)
        except OSError as exc:
            self._toast(f"Не удалось изменить автозапуск: {exc}")
            self._settings_reverting = True
            try:
                row.set_active(not enabled)
            finally:
                self._settings_reverting = False
            return
        self.store.set_setting("autostart", enabled)
        self._toast("Автозапуск включён" if enabled else "Автозапуск выключен")

    def _settings_tray(self, row: Adw.SwitchRow, _param=None) -> None:
        if self._settings_reverting:
            return
        enabled = bool(row.get_active())
        if enabled:
            if not self._try_start_tray(silent=False):
                self._settings_reverting = True
                try:
                    row.set_active(False)
                finally:
                    self._settings_reverting = False
                return
        else:
            self._tray.stop()
        self.store.set_setting("tray_enabled", enabled)

    def _try_start_tray(self, *, silent: bool) -> bool:
        ok = self._tray.start()
        if not ok and not silent:
            self._toast("Трей недоступен. Нужен AppIndicator и GTK3.")
        return ok

    def _core_subtitle(self) -> str:
        found = find_core(self.store)
        if found is None:
            return "Не найден — нажмите «Скачать»"
        return str(found)

    def _install_core_for_arch(
        self, arch: str, btn: "Gtk.Button", row: "Adw.ActionRow | None" = None,
        kernel_type: str = "xray",
    ) -> None:
        if self._core.is_running:
            self._toast("Сначала отключитесь, затем обновите ядро")
            return
        btn.set_sensitive(False)
        btn.set_label("Загрузка…")
        def progress(fraction: float, message: str) -> None:
            GLib.idle_add(self._core_progress, fraction, message, arch, kernel_type)
        def worker() -> None:
            try:
                path = install_core(progress, arch, kernel_type)
            except Exception as exc:
                GLib.idle_add(self._core_install_done, None, str(exc), arch, kernel_type)
            else:
                GLib.idle_add(self._core_install_done, str(path), None, arch, kernel_type)
        threading.Thread(target=worker, name="core-install", daemon=True).start()

    def _core_progress(
        self, fraction: float, message: str, arch: str, kernel_type: str
    ) -> bool:
        key = f"{arch}:{kernel_type}"
        row = self._core_tabs.get(key)
        if row is not None:
            row.set_subtitle(f"{message} {int(fraction * 100)}%")
        return False

    def _core_install_done(
        self,
        path: str | None,
        error: str | None,
        arch: str | None = None,
        kernel_type: str = "xray",
    ) -> bool:
        key = f"{arch}:{kernel_type}" if arch is not None else None
        row = self._core_tabs.get(key) if key else None
        btn = self._core_buttons.get(key) if key else None
        if row is not None:
            row.set_subtitle(self._core_hints.get(key, ""))
        if btn is not None:
            btn.set_sensitive(True)
            btn.set_label("Обновить" if path else "Скачать")
        label = "Amnezia Xray" if kernel_type == "amnezia-xray" else "Xray-core"
        if path:
            if kernel_type == "xray":
                self.store.set_setting("core_path", path)
            self._toast(f"{label} установлен")
        else:
            self._toast(f"Не удалось установить {label}: {error}")
        return False
    
    def _choose_core(self) -> None:
        dialog = Gtk.FileDialog(title="Выбрать бинарник Xray")
        dialog.open(self, None, self._core_file_chosen)

    def _core_file_chosen(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        if not file:
            return
        path = file.get_path()
        if not path:
            return
        self.store.set_setting("core_path", path)
        if hasattr(self, "core_row"):
            self.core_row.set_subtitle(self._core_subtitle())
        self._toast("Путь к Xray сохранён")

    def _check_core_async(self) -> None:
        xray = self.store.core_path()
        def worker() -> None:
            import subprocess
            try:
                result = subprocess.run(
                    [str(xray), "version"], capture_output=True, text=True, timeout=15
                )
                text = (result.stdout + result.stderr).strip() or f"код {result.returncode}"
            except Exception as exc:
                text = str(exc)
            GLib.idle_add(self._toast, f"Xray: {text.splitlines()[0]}")
        threading.Thread(target=worker, name="core-check", daemon=True).start()

    def _open_data_dir(self, *_args) -> None:
        try:
            Gio.AppInfo.launch_default_for_uri(paths.DATA_DIR.as_uri(), None)
        except GLib.Error as exc:
            self._toast(f"Не удалось открыть каталог: {exc.message}")

    # -------------------------------------------------------------------- log
    def _show_log(self) -> None:
        if self._log_dialog is not None:
            self._log_dialog.present(self)
            return
        dialog = Adw.Dialog()
        dialog.set_title("Журнал Xray")
        dialog.set_content_width(760)
        dialog.set_content_height(560)
        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(title="Журнал Xray", subtitle=str(paths.LOG_FILE))
        )
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh.add_css_class("flat")
        refresh.set_tooltip_text("Обновить")
        header.pack_end(refresh)
        toolbar.add_top_bar(header)
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        textview = Gtk.TextView()
        textview.set_editable(False)
        textview.set_cursor_visible(False)
        textview.set_monospace(True)
        textview.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        textview.set_margin_start(12)
        textview.set_margin_end(12)
        textview.set_margin_top(8)
        textview.set_margin_bottom(8)
        scrolled.set_child(textview)
        toolbar.set_content(scrolled)
        dialog.set_child(toolbar)
        buffer = textview.get_buffer()
        def update() -> None:
            text = self._core.log_text(40000) or "Журнал пока пуст."
            buffer.set_text(text)
            end = buffer.get_end_iter()
            textview.scroll_to_iter(end, 0.0, False, 0.0, 0.0)
        refresh.connect("clicked", lambda *_: update())
        update()
        def tick() -> bool:
            update()
            return True
        self._log_timeout = GLib.timeout_add(1500, tick)
        def closed(*_args) -> None:
            if self._log_timeout is not None:
                GLib.source_remove(self._log_timeout)
                self._log_timeout = None
            self._log_dialog = None
        dialog.connect("closed", closed)
        self._log_dialog = dialog
        dialog.present(self)

    # ------------------------------------------------------------------ kernels
    def _show_kernels_dialog(self) -> None:
        """Диалог «Ядра»: Xray и Amnezia Xray для архитектуры пользователя."""
        machine = current_arch()
        dialog = Adw.Dialog()
        dialog.set_title("Ядра")
        dialog.set_content_width(460)
        dialog.set_follows_content_size(True)
        dialog.set_presentation_mode(Adw.DialogPresentationMode.BOTTOM_SHEET)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(title="Ядра", subtitle=f"{machine} · v{paths.VERSION}")
        )
        toolbar.add_top_bar(header)

        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title="Доступные ядра",
            description="Загрузка для вашей архитектуры. Новое ядро применится при следующем подключении.",
        )
        kernels = (
            ("xray", "Xray-core", "Официальное ядро XTLS", "applications-system-symbolic"),
            ("amnezia-xray", "Amnezia Xray", "Сборка Xray от Amnezia", "security-high-symbolic"),
        )
        for kernel_type, title, hint, icon_name in kernels:
            try:
                asset_name(kernel_type, machine)
                supported = machine in SUPPORTED_ARCHS
            except RuntimeError:
                supported = False
            key = f"{machine}:{kernel_type}"
            subtitle = hint if supported else f"Недоступно для {machine}"
            self._core_hints[key] = subtitle

            row = Adw.ActionRow(title=title, subtitle=subtitle)
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(22)
            icon.add_css_class("kernel-icon")
            row.add_prefix(icon)

            btn = Gtk.Button(label="Скачать")
            btn.add_css_class("suggested-action")
            btn.add_css_class("kernel-btn")
            btn.set_valign(Gtk.Align.CENTER)
            btn.set_sensitive(supported)
            btn.set_tooltip_text(f"Скачать {title} для {machine}")
            btn.connect(
                "clicked",
                lambda *_, b=btn, r=row, kt=kernel_type: self._install_core_for_arch(
                    machine, b, r, kt
                ),
            )
            row.add_suffix(btn)
            self._core_tabs[key] = row
            self._core_buttons[key] = btn
            group.add(row)

        page.add(group)
        toolbar.set_content(page)
        dialog.set_child(toolbar)
        dialog.present(self)
    # ------------------------------------------------------------------ about
    def _about_dialog(self) -> None:
        """Диалог «О программе» (Adw.AboutDialog): версия + 2 кнопки."""
        dialog = Adw.AboutDialog(
            application_name=paths.APP_TITLE,
            application_icon=paths.ICON_NAME,
            developer_name="Dma2ray contributors",
            version=paths.VERSION,
            comments=(
                "Клиент VLESS для Linux на GTK4/libadwaita.\n"
                "Ядро — Xray-core, включая нативный TUN-режим.\n"
                "Клиент создан на базе Xray — благодарности разработчику "
                "этого ядра: https://github.com/XTLS/Xray-core"
            ),
            website="https://github.com/XTLS/Xray-core",
            license_type=Gtk.License.GPL_3_0_ONLY,
        )
        dialog.present(self)

    # ---------------------------------------------------------------- helpers
    def _toast(self, message: str) -> None:
        toast = Adw.Toast.new(message)
        toast.set_timeout(4)
        self.toast_overlay.add_toast(toast)
