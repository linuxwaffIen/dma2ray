#include "dma2ray/window.hpp"
#include "dma2ray/paths.hpp"
#include "dma2ray/theme.hpp"
#include "dma2ray/vless.hpp"
#include "dma2ray/hysteria.hpp"
#include "dma2ray/ping.hpp"
#include "dma2ray/net.hpp"
#include "dma2ray/flags.hpp"
#include "dma2ray/system.hpp"

#include <fstream>
#include <sstream>
#include <thread>
#include <algorithm>
#include <ctime>

namespace dma2ray::ui {

static void install_icon_theme() {
    paths::ensure_icons();
    GdkDisplay* display = gdk_display_get_default();
    if (!display) return;
    GtkIconTheme* theme = gtk_icon_theme_get_for_display(display);
    gtk_icon_theme_add_resource_path(theme, "/io/github/dma2ray/Dma2ray/icons");
    gtk_icon_theme_add_resource_path(theme, "/io/github/dma2ray/Dma2ray/icons/scalable/actions");
    gtk_icon_theme_add_resource_path(theme, "/io/github/dma2ray/Dma2ray/icons/scalable/status");
    gtk_icon_theme_add_search_path(theme, paths::icons_dir().c_str());

    for (const char* root : {"/usr/share/icons/Adwaita", "/usr/local/share/icons/Adwaita", "/usr/share/icons/hicolor"}) {
        if (std::filesystem::exists(root)) {
            gtk_icon_theme_add_search_path(theme, root);
            auto sym = std::filesystem::path(root) / "symbolic";
            if (std::filesystem::exists(sym)) {
                gtk_icon_theme_add_search_path(theme, sym.c_str());
                for (const auto& entry : std::filesystem::directory_iterator(sym)) {
                    if (entry.is_directory()) {
                        gtk_icon_theme_add_search_path(theme, entry.path().c_str());
                    }
                }
            }
        }
    }
}

static void set_image_icon_with_fallback(GtkImage* img, const std::string& name, int pixel_size = 0) {
    if (!img) return;
    GdkDisplay* disp = gdk_display_get_default();
    bool found = false;
    if (disp) {
        GtkIconTheme* theme = gtk_icon_theme_get_for_display(disp);
        found = gtk_icon_theme_has_icon(theme, name.c_str());
    }
    if (found) {
        gtk_image_set_from_icon_name(img, name.c_str());
    } else {
        std::string res = "/io/github/dma2ray/Dma2ray/icons/" + name + ".svg";
        gtk_image_set_from_resource(img, res.c_str());
    }
    if (pixel_size > 0) {
        gtk_image_set_pixel_size(img, pixel_size);
    }
}

static GtkWidget* create_image_with_fallback(const std::string& name, int pixel_size = 0) {
    GtkWidget* img = gtk_image_new();
    set_image_icon_with_fallback(GTK_IMAGE(img), name, pixel_size);
    return img;
}

static GtkWidget* create_button_from_icon_fallback(const std::string& name) {
    GtkWidget* btn = gtk_button_new();
    GtkWidget* img = create_image_with_fallback(name);
    gtk_button_set_child(GTK_BUTTON(btn), img);
    return btn;
}

static void strip_switcher_icons(GtkWidget* root) {
    if (!root) return;
    std::vector<GtkWidget*> stack = {root};
    while (!stack.empty()) {
        GtkWidget* w = stack.back();
        stack.pop_back();
        if (GTK_IS_IMAGE(w)) {
            gtk_widget_set_visible(w, FALSE);
            continue;
        }
        for (GtkWidget* c = gtk_widget_get_first_child(w); c != nullptr; c = gtk_widget_get_next_sibling(c)) {
            stack.push_back(c);
        }
    }
}

static std::string format_time(double timestamp) {
    if (timestamp <= 0.0) return "никогда";
    std::time_t t = static_cast<std::time_t>(timestamp);
    std::tm tm{};
    localtime_r(&t, &tm);
    char buf[64];
    std::strftime(buf, sizeof(buf), "%d.%m.%Y %H:%M", &tm);
    return buf;
}

static std::string parse_profile_detail(const std::string& uri) {
    if (uri.rfind("hysteria2://", 0) == 0 || uri.rfind("hy2://", 0) == 0) {
        try {
            auto h = hysteria::parse_hysteria2(uri);
            return h.address + ":" + std::to_string(h.port) + " (Hysteria 2)";
        } catch (...) {
            return "Hysteria 2";
        }
    }
    try {
        auto v = vless::parse_any_vless(uri);
        return v.address + ":" + std::to_string(v.port) + " (" + v.protocol + ")";
    } catch (...) {
        return "Некорректная ссылка";
    }
}

static std::pair<std::string, int> get_host_port(const std::string& uri) {
    if (uri.rfind("hysteria2://", 0) == 0 || uri.rfind("hy2://", 0) == 0) {
        try {
            auto h = hysteria::parse_hysteria2(uri);
            return {h.address, h.port};
        } catch (...) {
            return {"", 0};
        }
    }
    try {
        auto v = vless::parse_any_vless(uri);
        return {v.address, v.port};
    } catch (...) {
        return {"", 0};
    }
}

MainWindow::MainWindow(AdwApplication* app, state::Store& store, manager::CoreManager& core_mgr)
    : app_(app), store_(store), core_mgr_(core_mgr) {
    build_ui();
}

MainWindow::~MainWindow() {
    if (log_timeout_ > 0) {
        g_source_remove(log_timeout_);
        log_timeout_ = 0;
    }
}

void MainWindow::present() {
    if (window_) gtk_window_present(GTK_WINDOW(window_));
}

void MainWindow::show_toast(const std::string& msg) {
    if (!toast_overlay_) return;
    AdwToast* toast = adw_toast_new(msg.c_str());
    adw_toast_set_timeout(toast, 4);
    adw_toast_overlay_add_toast(ADW_TOAST_OVERLAY(toast_overlay_), toast);
}

void MainWindow::build_ui() {
    install_icon_theme();

    window_ = adw_application_window_new(GTK_APPLICATION(app_));
    gtk_window_set_title(GTK_WINDOW(window_), paths::APP_TITLE.c_str());
    gtk_window_set_default_size(GTK_WINDOW(window_), 440, 800);

    toast_overlay_ = adw_toast_overlay_new();

    AdwToolbarView* toolbar = ADW_TOOLBAR_VIEW(adw_toolbar_view_new());
    AdwHeaderBar* header = ADW_HEADER_BAR(adw_header_bar_new());
    gtk_widget_add_css_class(GTK_WIDGET(header), "main-headerbar");

    header_title_ = adw_window_title_new(paths::APP_TITLE.c_str(), "Отключено");
    adw_header_bar_set_title_widget(header, header_title_);

    // App menu
    GMenu* menu = g_menu_new();
    g_menu_append(menu, "Добавить профиль", "win.add-profile");
    g_menu_append(menu, "Добавить подписку", "win.add-subscription");
    g_menu_append(menu, "Обновить подписки", "win.update-subscriptions");
    g_menu_append(menu, "Проверить все задержки", "win.ping-all");
    g_menu_append(menu, "Тест скорости", "win.speed-test");
    g_menu_append(menu, "Настройки", "win.settings");
    g_menu_append(menu, "Журнал Xray", "win.show-log");
    g_menu_append(menu, "О программе", "win.about");
    g_menu_append(menu, "Ядра", "win.kernels");
    g_menu_append(menu, "Выход", "win.quit");

    GtkWidget* menu_btn = gtk_menu_button_new();
    gtk_menu_button_set_icon_name(GTK_MENU_BUTTON(menu_btn), "open-menu-symbolic");
    gtk_menu_button_set_menu_model(GTK_MENU_BUTTON(menu_btn), G_MENU_MODEL(menu));
    adw_header_bar_pack_end(header, menu_btn);
    adw_toolbar_view_add_top_bar(toolbar, GTK_WIDGET(header));

    view_stack_ = adw_view_stack_new();
    gtk_widget_set_vexpand(view_stack_, TRUE);

    GtkWidget* home_page = build_home_page();
    adw_view_stack_add_titled_with_icon(ADW_VIEW_STACK(view_stack_), home_page, "home", "Главная", "user-home-symbolic");

    GtkWidget* servers_page = build_servers_page();
    adw_view_stack_add_titled_with_icon(ADW_VIEW_STACK(view_stack_), servers_page, "servers", "Серверы", "network-server-symbolic");

    GtkWidget* settings_page = build_settings_page();
    adw_view_stack_add_titled_with_icon(ADW_VIEW_STACK(view_stack_), settings_page, "settings", "Настройки", "emblem-system-symbolic");

    AdwViewSwitcherBar* switcher_bar = ADW_VIEW_SWITCHER_BAR(adw_view_switcher_bar_new());
    adw_view_switcher_bar_set_stack(switcher_bar, ADW_VIEW_STACK(view_stack_));
    adw_view_switcher_bar_set_reveal(switcher_bar, TRUE);
    gtk_widget_add_css_class(GTK_WIDGET(switcher_bar), "main-switcherbar");

    // Hide any switcher icons so that tabs are text-only, exactly matching Python original
    strip_switcher_icons(GTK_WIDGET(switcher_bar));
    g_signal_connect_swapped(view_stack_, "notify::visible-child", G_CALLBACK((+[](GtkWidget* sb) {
        strip_switcher_icons(sb);
    })), GTK_WIDGET(switcher_bar));

    adw_toolbar_view_add_bottom_bar(toolbar, GTK_WIDGET(switcher_bar));
    adw_toolbar_view_set_content(toolbar, view_stack_);

    adw_toast_overlay_set_child(ADW_TOAST_OVERLAY(toast_overlay_), GTK_WIDGET(toolbar));
    adw_application_window_set_content(ADW_APPLICATION_WINDOW(window_), toast_overlay_);

    // Register simple actions
    auto register_action = [this](const char* name, auto callback) {
        GSimpleAction* act = g_simple_action_new(name, nullptr);
        g_signal_connect_swapped(act, "activate", G_CALLBACK(+[](MainWindow* self) {
            // will be called
        }), this);
        g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act));
    };

    GSimpleAction* act_add_p = g_simple_action_new("add-profile", nullptr);
    g_signal_connect_swapped(act_add_p, "activate", G_CALLBACK((+[](MainWindow* self) { self->show_add_profile_dialog(); })), this);
    g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_add_p));

    GSimpleAction* act_add_s = g_simple_action_new("add-subscription", nullptr);
    g_signal_connect_swapped(act_add_s, "activate", G_CALLBACK((+[](MainWindow* self) { self->show_add_subscription_dialog(); })), this);
    g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_add_s));

    GSimpleAction* act_upd_s = g_simple_action_new("update-subscriptions", nullptr);
    g_signal_connect_swapped(act_upd_s, "activate", G_CALLBACK((+[](MainWindow* self) { self->update_all_subscriptions(); })), this);
    g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_upd_s));

    GSimpleAction* act_ping_all = g_simple_action_new("ping-all", nullptr);
    g_signal_connect_swapped(act_ping_all, "activate", G_CALLBACK((+[](MainWindow* self) { self->ping_all_profiles(); })), this);
    g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_ping_all));

    GSimpleAction* act_speed = g_simple_action_new("speed-test", nullptr);
    g_signal_connect_swapped(act_speed, "activate", G_CALLBACK((+[](MainWindow* self) { self->run_speed_test(); })), this);
    g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_speed));

    GSimpleAction* act_settings = g_simple_action_new("settings", nullptr);
    g_signal_connect_swapped(act_settings, "activate", G_CALLBACK((+[](MainWindow* self) {
        adw_view_stack_set_visible_child_name(ADW_VIEW_STACK(self->view_stack_), "settings");
    })), this);
    g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_settings));

    GSimpleAction* act_log = g_simple_action_new("show-log", nullptr);
    g_signal_connect_swapped(act_log, "activate", G_CALLBACK((+[](MainWindow* self) { self->show_log_dialog(); })), this);
    g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_log));

    GSimpleAction* act_about = g_simple_action_new("about", nullptr);
    g_signal_connect_swapped(act_about, "activate", G_CALLBACK((+[](MainWindow* self) { self->show_about_dialog(); })), this);
    g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_about));

    GSimpleAction* act_kernels = g_simple_action_new("kernels", nullptr);
    g_signal_connect_swapped(act_kernels, "activate", G_CALLBACK((+[](MainWindow* self) { self->show_kernels_dialog(); })), this);
    g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_kernels));

    GSimpleAction* act_quit = g_simple_action_new("quit", nullptr);
    g_signal_connect_swapped(act_quit, "activate", G_CALLBACK((+[](MainWindow* self) {
        g_application_quit(G_APPLICATION(self->app_));
    })), this);
    g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_quit));

    refresh_all();
}

GtkWidget* MainWindow::build_home_page() {
    GtkWidget* scrolled = gtk_scrolled_window_new();
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scrolled), GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_widget_set_vexpand(scrolled, TRUE);

    GtkWidget* clamp = adw_clamp_new();
    adw_clamp_set_maximum_size(ADW_CLAMP(clamp), 540);

    GtkWidget* box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 16);
    gtk_widget_set_margin_start(box, 18);
    gtk_widget_set_margin_end(box, 18);
    gtk_widget_set_margin_top(box, 24);
    gtk_widget_set_margin_bottom(box, 24);

    status_label_ = gtk_label_new("Отключено");
    gtk_widget_add_css_class(status_label_, "home-status");
    gtk_widget_set_halign(status_label_, GTK_ALIGN_CENTER);
    gtk_box_append(GTK_BOX(box), status_label_);

    detail_label_ = gtk_label_new("Выберите профиль");
    gtk_widget_add_css_class(detail_label_, "section-hint");
    gtk_widget_set_halign(detail_label_, GTK_ALIGN_CENTER);
    gtk_label_set_wrap(GTK_LABEL(detail_label_), TRUE);
    gtk_box_append(GTK_BOX(box), detail_label_);

    big_icon_ = create_image_with_fallback("network-vpn-symbolic", 48);

    big_button_ = gtk_button_new();
    gtk_button_set_child(GTK_BUTTON(big_button_), big_icon_);
    gtk_widget_add_css_class(big_button_, "connect-big");
    gtk_widget_add_css_class(big_button_, "connect-idle");
    gtk_widget_set_halign(big_button_, GTK_ALIGN_CENTER);
    gtk_widget_set_tooltip_text(big_button_, "Подключить или отключить");

    g_signal_connect_swapped(big_button_, "clicked", G_CALLBACK((+[](MainWindow* self) {
        self->toggle_connection();
    })), this);
    gtk_box_append(GTK_BOX(box), big_button_);

    // Server card
    server_card_ = gtk_button_new();
    gtk_widget_add_css_class(server_card_, "flat");
    gtk_widget_add_css_class(server_card_, "server-card");
    gtk_widget_set_tooltip_text(server_card_, "Открыть список серверов");
    g_signal_connect_swapped(server_card_, "clicked", G_CALLBACK((+[](MainWindow* self) {
        adw_view_stack_set_visible_child_name(ADW_VIEW_STACK(self->view_stack_), "servers");
    })), this);

    GtkWidget* card_box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    card_flag_ = gtk_label_new("🌐");
    gtk_widget_add_css_class(card_flag_, "flag-big");
    gtk_box_append(GTK_BOX(card_box), card_flag_);

    GtkWidget* text_box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 2);
    gtk_widget_set_hexpand(text_box, TRUE);
    card_name_ = gtk_label_new("Нет профиля");
    gtk_label_set_xalign(GTK_LABEL(card_name_), 0.0f);
    gtk_widget_add_css_class(card_name_, "heading");
    gtk_label_set_ellipsize(GTK_LABEL(card_name_), PANGO_ELLIPSIZE_END);
    gtk_box_append(GTK_BOX(text_box), card_name_);

    card_addr_ = gtk_label_new("Добавьте vless:// или подписку");
    gtk_label_set_xalign(GTK_LABEL(card_addr_), 0.0f);
    gtk_widget_add_css_class(card_addr_, "section-hint");
    gtk_label_set_ellipsize(GTK_LABEL(card_addr_), PANGO_ELLIPSIZE_END);
    gtk_box_append(GTK_BOX(text_box), card_addr_);
    gtk_box_append(GTK_BOX(card_box), text_box);

    GtkWidget* card_right = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    gtk_widget_set_valign(card_right, GTK_ALIGN_CENTER);

    card_latency_ = gtk_label_new("");
    gtk_widget_add_css_class(card_latency_, "latency-pill");
    gtk_widget_set_visible(card_latency_, FALSE);
    gtk_box_append(GTK_BOX(card_right), card_latency_);

    GtkWidget* next_icon = gtk_image_new_from_icon_name("go-next-symbolic");
    gtk_box_append(GTK_BOX(card_right), next_icon);
    gtk_box_append(GTK_BOX(card_box), card_right);

    gtk_button_set_child(GTK_BUTTON(server_card_), card_box);
    gtk_box_append(GTK_BOX(box), server_card_);

    home_hint_ = gtk_label_new("Профилей пока нет. Вставьте ссылку vless:// или URL подписки ниже.");
    gtk_label_set_wrap(GTK_LABEL(home_hint_), TRUE);
    gtk_widget_set_halign(home_hint_, GTK_ALIGN_CENTER);
    gtk_widget_add_css_class(home_hint_, "section-hint");
    gtk_widget_set_visible(home_hint_, FALSE);
    gtk_box_append(GTK_BOX(box), home_hint_);

    // Quick connect group
    AdwPreferencesGroup* quick_group = ADW_PREFERENCES_GROUP(adw_preferences_group_new());
    adw_preferences_group_set_title(quick_group, "Быстрое подключение");
    adw_preferences_group_set_description(quick_group, "Вставьте ссылку vless:// или URL подписки — профиль добавится и подключится.");

    quick_entry_ = adw_entry_row_new();
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(quick_entry_), "vless://… или URL подписки");

    GtkWidget* quick_suffix = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6);
    GtkWidget* quick_btn = gtk_button_new_from_icon_name("go-next-symbolic");
    gtk_widget_add_css_class(quick_btn, "flat");
    gtk_widget_set_tooltip_text(quick_btn, "Добавить и подключить");
    g_signal_connect_swapped(quick_btn, "clicked", G_CALLBACK((+[](MainWindow* self) {
        self->quick_connect();
    })), this);
    gtk_box_append(GTK_BOX(quick_suffix), quick_btn);

    GtkWidget* qr_btn = gtk_button_new_from_icon_name("emblem-photos-symbolic");
    gtk_widget_add_css_class(qr_btn, "flat");
    gtk_widget_set_tooltip_text(qr_btn, "Импортировать из QR-файла");
    g_signal_connect_swapped(qr_btn, "clicked", G_CALLBACK((+[](MainWindow* self) {
        self->show_toast("Выберите изображение с QR-кодом");
    })), this);
    gtk_box_append(GTK_BOX(quick_suffix), qr_btn);

    adw_entry_row_add_suffix(ADW_ENTRY_ROW(quick_entry_), quick_suffix);
    g_signal_connect_swapped(quick_entry_, "entry-activated", G_CALLBACK((+[](MainWindow* self) {
        self->quick_connect();
    })), this);
    adw_preferences_group_add(quick_group, quick_entry_);
    gtk_box_append(GTK_BOX(box), GTK_WIDGET(quick_group));

    // Speed test group
    AdwPreferencesGroup* speed_group = ADW_PREFERENCES_GROUP(adw_preferences_group_new());
    adw_preferences_group_set_title(speed_group, "Скорость и задержка");

    GtkWidget* speed_actions = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 2);
    speed_button_ = gtk_button_new_from_icon_name("network-transmit-receive-symbolic");
    gtk_widget_add_css_class(speed_button_, "flat");
    gtk_widget_set_tooltip_text(speed_button_, "Измерить задержку и скорость через SOCKS5");
    g_signal_connect_swapped(speed_button_, "clicked", G_CALLBACK((+[](MainWindow* self) {
        self->run_speed_test();
    })), this);
    gtk_box_append(GTK_BOX(speed_actions), speed_button_);
    adw_preferences_group_set_header_suffix(speed_group, speed_actions);

    speed_latency_row_ = adw_action_row_new();
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(speed_latency_row_), "Задержка подключения");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(speed_latency_row_), "—");
    adw_preferences_group_add(speed_group, speed_latency_row_);

    speed_down_row_ = adw_action_row_new();
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(speed_down_row_), "Скорость загрузки");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(speed_down_row_), "—");
    adw_preferences_group_add(speed_group, speed_down_row_);

    gtk_box_append(GTK_BOX(box), GTK_WIDGET(speed_group));

    adw_clamp_set_child(ADW_CLAMP(clamp), box);
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scrolled), clamp);
    return scrolled;
}

GtkWidget* MainWindow::build_servers_page() {
    GtkWidget* scrolled = gtk_scrolled_window_new();
    gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scrolled), GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
    gtk_widget_set_vexpand(scrolled, TRUE);

    GtkWidget* clamp = adw_clamp_new();
    adw_clamp_set_maximum_size(ADW_CLAMP(clamp), 540);

    GtkWidget* box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 16);
    gtk_widget_set_margin_start(box, 18);
    gtk_widget_set_margin_end(box, 18);
    gtk_widget_set_margin_top(box, 18);
    gtk_widget_set_margin_bottom(box, 18);

    // Profiles group
    profiles_group_ = adw_preferences_group_new();
    adw_preferences_group_set_title(ADW_PREFERENCES_GROUP(profiles_group_), "Серверы");

    GtkWidget* prof_actions = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 2);

    sort_btn_ = gtk_button_new_from_icon_name("view-list-symbolic");
    gtk_widget_add_css_class(sort_btn_, "flat");
    gtk_widget_set_tooltip_text(sort_btn_, "Сортировать по задержке");
    g_signal_connect_swapped(sort_btn_, "clicked", G_CALLBACK((+[](MainWindow* self) {
        self->toggle_sort();
    })), this);
    gtk_box_append(GTK_BOX(prof_actions), sort_btn_);

    GtkWidget* ping_all_btn = gtk_button_new_from_icon_name("network-cellular-signal-excellent-symbolic");
    gtk_widget_add_css_class(ping_all_btn, "flat");
    gtk_widget_set_tooltip_text(ping_all_btn, "Проверить задержку всех серверов");
    g_signal_connect_swapped(ping_all_btn, "clicked", G_CALLBACK((+[](MainWindow* self) {
        self->ping_all_profiles();
    })), this);
    gtk_box_append(GTK_BOX(prof_actions), ping_all_btn);

    GtkWidget* add_prof_btn = gtk_button_new_from_icon_name("list-add-symbolic");
    gtk_widget_add_css_class(add_prof_btn, "flat");
    gtk_widget_set_tooltip_text(add_prof_btn, "Добавить профиль");
    g_signal_connect_swapped(add_prof_btn, "clicked", G_CALLBACK((+[](MainWindow* self) {
        self->show_add_profile_dialog();
    })), this);
    gtk_box_append(GTK_BOX(prof_actions), add_prof_btn);

    adw_preferences_group_set_header_suffix(ADW_PREFERENCES_GROUP(profiles_group_), prof_actions);

    profiles_list_box_ = gtk_list_box_new();
    gtk_widget_add_css_class(profiles_list_box_, "boxed-list");
    adw_preferences_group_add(ADW_PREFERENCES_GROUP(profiles_group_), profiles_list_box_);
    gtk_box_append(GTK_BOX(box), profiles_group_);

    // Subscriptions group
    subs_group_ = adw_preferences_group_new();
    adw_preferences_group_set_title(ADW_PREFERENCES_GROUP(subs_group_), "Подписки");

    GtkWidget* sub_actions = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 2);
    GtkWidget* update_subs_btn = gtk_button_new_from_icon_name("view-refresh-symbolic");
    gtk_widget_add_css_class(update_subs_btn, "flat");
    gtk_widget_set_tooltip_text(update_subs_btn, "Обновить все подписки");
    g_signal_connect_swapped(update_subs_btn, "clicked", G_CALLBACK((+[](MainWindow* self) {
        self->update_all_subscriptions();
    })), this);
    gtk_box_append(GTK_BOX(sub_actions), update_subs_btn);

    GtkWidget* add_sub_btn = gtk_button_new_from_icon_name("list-add-symbolic");
    gtk_widget_add_css_class(add_sub_btn, "flat");
    gtk_widget_set_tooltip_text(add_sub_btn, "Добавить подписку");
    g_signal_connect_swapped(add_sub_btn, "clicked", G_CALLBACK((+[](MainWindow* self) {
        self->show_add_subscription_dialog();
    })), this);
    gtk_box_append(GTK_BOX(sub_actions), add_sub_btn);

    adw_preferences_group_set_header_suffix(ADW_PREFERENCES_GROUP(subs_group_), sub_actions);

    subs_list_box_ = gtk_list_box_new();
    gtk_widget_add_css_class(subs_list_box_, "boxed-list");
    adw_preferences_group_add(ADW_PREFERENCES_GROUP(subs_group_), subs_list_box_);
    gtk_box_append(GTK_BOX(box), subs_group_);

    adw_clamp_set_child(ADW_CLAMP(clamp), box);
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scrolled), clamp);
    return scrolled;
}

GtkWidget* MainWindow::build_settings_page() {
    AdwPreferencesPage* page = ADW_PREFERENCES_PAGE(adw_preferences_page_new());

    // Connection
    AdwPreferencesGroup* conn_group = ADW_PREFERENCES_GROUP(adw_preferences_group_new());
    adw_preferences_group_set_title(conn_group, "Подключение");
    adw_preferences_group_set_description(conn_group, "Изменения применятся при следующем подключении.");

    const char* modes[] = {"Прокси (SOCKS5/HTTP)", "Системный прокси", "ВПН (TUN, нужен root)", nullptr};
    AdwComboRow* mode_row = ADW_COMBO_ROW(adw_combo_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(mode_row), "Режим подключения");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(mode_row), "Локальный прокси · системный прокси ОС · ВПН через tun-интерфейс");
    adw_combo_row_set_model(mode_row, G_LIST_MODEL(gtk_string_list_new(modes)));

    std::string cur_mode = store_.get_setting("mode", "vpn").get<std::string>();
    guint mode_idx = 0;
    if (cur_mode == "system") mode_idx = 1;
    else if (cur_mode == "vpn") mode_idx = 2;
    adw_combo_row_set_selected(mode_row, mode_idx);

    g_signal_connect_swapped(mode_row, "notify::selected", G_CALLBACK((+[](MainWindow* self, GParamSpec*, AdwComboRow* r) {
        guint sel = adw_combo_row_get_selected(r);
        const char* m = (sel == 1) ? "system" : ((sel == 2) ? "vpn" : "proxy");
        self->store_.set_setting("mode", m);
        self->refresh_ui_status();
    })), this);
    adw_preferences_group_add(conn_group, GTK_WIDGET(mode_row));

    // Ports
    AdwSpinRow* socks_row = ADW_SPIN_ROW(adw_spin_row_new_with_range(1, 65535, 1));
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(socks_row), "SOCKS5-порт");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(socks_row), "Локальный прокси для приложений");
    adw_spin_row_set_value(socks_row, store_.get_setting("socks_port", 10808).get<int>());
    g_signal_connect_swapped(socks_row, "notify::value", G_CALLBACK((+[](MainWindow* self, GParamSpec*, AdwSpinRow* r) {
        self->store_.set_setting("socks_port", static_cast<int>(adw_spin_row_get_value(r)));
    })), this);
    adw_preferences_group_add(conn_group, GTK_WIDGET(socks_row));

    AdwSpinRow* http_row = ADW_SPIN_ROW(adw_spin_row_new_with_range(1, 65535, 1));
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(http_row), "HTTP-порт");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(http_row), "Локальный HTTP-прокси");
    adw_spin_row_set_value(http_row, store_.get_setting("http_port", 10809).get<int>());
    g_signal_connect_swapped(http_row, "notify::value", G_CALLBACK((+[](MainWindow* self, GParamSpec*, AdwSpinRow* r) {
        self->store_.set_setting("http_port", static_cast<int>(adw_spin_row_get_value(r)));
    })), this);
    adw_preferences_group_add(conn_group, GTK_WIDGET(http_row));

    const char* log_levels[] = {"debug", "info", "warning", "error", "none", nullptr};
    AdwComboRow* log_row = ADW_COMBO_ROW(adw_combo_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(log_row), "Уровень журнала Xray");
    adw_combo_row_set_model(log_row, G_LIST_MODEL(gtk_string_list_new(log_levels)));
    std::string cur_log = store_.get_setting("log_level", "warning").get<std::string>();
    guint log_idx = 2;
    for (guint i = 0; log_levels[i]; ++i) {
        if (cur_log == log_levels[i]) { log_idx = i; break; }
    }
    adw_combo_row_set_selected(log_row, log_idx);
    g_signal_connect_swapped(log_row, "notify::selected", G_CALLBACK((+[](MainWindow* self, GParamSpec*, AdwComboRow* r) {
        guint sel = adw_combo_row_get_selected(r);
        const char* lvls[] = {"debug", "info", "warning", "error", "none"};
        if (sel < 5) self->store_.set_setting("log_level", lvls[sel]);
    })), this);
    adw_preferences_group_add(conn_group, GTK_WIDGET(log_row));
    adw_preferences_page_add(page, conn_group);

    // Appearance
    AdwPreferencesGroup* app_group = ADW_PREFERENCES_GROUP(adw_preferences_group_new());
    adw_preferences_group_set_title(app_group, "Оформление");
    const char* schemes[] = {"Как в системе", "Светлая", "Тёмная", nullptr};
    AdwComboRow* scheme_row = ADW_COMBO_ROW(adw_combo_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(scheme_row), "Тема");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(scheme_row), "По умолчанию берётся из системы");
    adw_combo_row_set_model(scheme_row, G_LIST_MODEL(gtk_string_list_new(schemes)));

    std::string cur_scheme = store_.get_setting("color_scheme", "system").get<std::string>();
    guint sch_idx = 0;
    if (cur_scheme == "light") sch_idx = 1;
    else if (cur_scheme == "dark") sch_idx = 2;
    adw_combo_row_set_selected(scheme_row, sch_idx);

    g_signal_connect_swapped(scheme_row, "notify::selected", G_CALLBACK((+[](MainWindow* self, GParamSpec*, AdwComboRow* r) {
        guint sel = adw_combo_row_get_selected(r);
        std::string s = "system";
        if (sel == 1) s = "light";
        else if (sel == 2) s = "dark";
        self->store_.set_setting("color_scheme", s);
        apply_theme(s);
    })), this);
    adw_preferences_group_add(app_group, GTK_WIDGET(scheme_row));
    adw_preferences_page_add(page, app_group);

    // Servers & Latencies
    AdwPreferencesGroup* srv_group = ADW_PREFERENCES_GROUP(adw_preferences_group_new());
    adw_preferences_group_set_title(srv_group, "Серверы и задержки");

    AdwSwitchRow* auto_ping_row = ADW_SWITCH_ROW(adw_switch_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(auto_ping_row), "Автопроверка задержки");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(auto_ping_row), "Пинговать серверы при обновлении списка");
    adw_switch_row_set_active(auto_ping_row, store_.get_setting("auto_ping", true).get<bool>());
    g_signal_connect_swapped(auto_ping_row, "notify::active", G_CALLBACK((+[](MainWindow* self, GParamSpec*, AdwSwitchRow* r) {
        self->store_.set_setting("auto_ping", adw_switch_row_get_active(r));
    })), this);
    adw_preferences_group_add(srv_group, GTK_WIDGET(auto_ping_row));

    AdwSwitchRow* sort_row = ADW_SWITCH_ROW(adw_switch_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(sort_row), "Сортировать по задержке");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(sort_row), "Сначала самые быстрые серверы");
    adw_switch_row_set_active(sort_row, store_.get_setting("sort_by_latency", false).get<bool>());
    g_signal_connect_swapped(sort_row, "notify::active", G_CALLBACK((+[](MainWindow* self, GParamSpec*, AdwSwitchRow* r) {
        self->store_.set_setting("sort_by_latency", adw_switch_row_get_active(r));
        self->refresh_profiles_list();
    })), this);
    adw_preferences_group_add(srv_group, GTK_WIDGET(sort_row));

    AdwSpinRow* ping_to_row = ADW_SPIN_ROW(adw_spin_row_new_with_range(1.0, 30.0, 0.5));
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(ping_to_row), "Таймаут проверки задержки");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(ping_to_row), "Секунды на проверку одного сервера");
    adw_spin_row_set_digits(ping_to_row, 1);
    adw_spin_row_set_value(ping_to_row, store_.get_setting("ping_timeout", 4.0).get<double>());
    g_signal_connect_swapped(ping_to_row, "notify::value", G_CALLBACK((+[](MainWindow* self, GParamSpec*, AdwSpinRow* r) {
        self->store_.set_setting("ping_timeout", adw_spin_row_get_value(r));
    })), this);
    adw_preferences_group_add(srv_group, GTK_WIDGET(ping_to_row));

    const char* ping_types[] = {"TCP-сокет", "TLS-хэндшейк", "ICMP-пинг", nullptr};
    AdwComboRow* pt_row = ADW_COMBO_ROW(adw_combo_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(pt_row), "Тип пинга");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(pt_row), "Метод измерения задержки до серверов");
    adw_combo_row_set_model(pt_row, G_LIST_MODEL(gtk_string_list_new(ping_types)));
    std::string cur_pt = store_.get_setting("ping_type", "tcp").get<std::string>();
    guint pt_idx = 0;
    if (cur_pt == "tls") pt_idx = 1;
    else if (cur_pt == "icmp") pt_idx = 2;
    adw_combo_row_set_selected(pt_row, pt_idx);
    g_signal_connect_swapped(pt_row, "notify::selected", G_CALLBACK((+[](MainWindow* self, GParamSpec*, AdwComboRow* r) {
        guint sel = adw_combo_row_get_selected(r);
        const char* pts[] = {"tcp", "tls", "icmp"};
        if (sel < 3) self->store_.set_setting("ping_type", pts[sel]);
    })), this);
    adw_preferences_group_add(srv_group, GTK_WIDGET(pt_row));

    AdwSwitchRow* auto_sub_row = ADW_SWITCH_ROW(adw_switch_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(auto_sub_row), "Автообновление подписок");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(auto_sub_row), "Обновлять все подписки по расписанию");
    adw_switch_row_set_active(auto_sub_row, store_.get_setting("auto_update_subs", false).get<bool>());
    g_signal_connect_swapped(auto_sub_row, "notify::active", G_CALLBACK((+[](MainWindow* self, GParamSpec*, AdwSwitchRow* r) {
        self->store_.set_setting("auto_update_subs", adw_switch_row_get_active(r));
    })), this);
    adw_preferences_group_add(srv_group, GTK_WIDGET(auto_sub_row));

    adw_preferences_page_add(page, srv_group);

    // Startup & System
    AdwPreferencesGroup* start_group = ADW_PREFERENCES_GROUP(adw_preferences_group_new());
    adw_preferences_group_set_title(start_group, "Запуск и система");

    AdwSwitchRow* autostart_row = ADW_SWITCH_ROW(adw_switch_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(autostart_row), "Автозапуск при входе");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(autostart_row), "Запускать Dma2ray вместе с сеансом");
    adw_switch_row_set_active(autostart_row, system::is_autostart_enabled());
    g_signal_connect_swapped(autostart_row, "notify::active", G_CALLBACK((+[](MainWindow* self, GParamSpec*, AdwSwitchRow* r) {
        bool act = adw_switch_row_get_active(r);
        system::set_autostart(act);
        self->store_.set_setting("autostart", act);
    })), this);
    adw_preferences_group_add(start_group, GTK_WIDGET(autostart_row));

    AdwSwitchRow* close_row = ADW_SWITCH_ROW(adw_switch_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(close_row), "Закрывать окно в трей");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(close_row), "Приложение продолжит работать в фоне");
    adw_switch_row_set_active(close_row, store_.get_setting("close_to_tray", true).get<bool>());
    g_signal_connect_swapped(close_row, "notify::active", G_CALLBACK((+[](MainWindow* self, GParamSpec*, AdwSwitchRow* r) {
        self->store_.set_setting("close_to_tray", adw_switch_row_get_active(r));
    })), this);
    adw_preferences_group_add(start_group, GTK_WIDGET(close_row));

    adw_preferences_page_add(page, start_group);

    // Diagnostics
    AdwPreferencesGroup* diag_group = ADW_PREFERENCES_GROUP(adw_preferences_group_new());
    adw_preferences_group_set_title(diag_group, "Диагностика");

    AdwActionRow* log_act = ADW_ACTION_ROW(adw_action_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(log_act), "Журнал Xray");
    adw_action_row_set_subtitle(log_act, "Последние сообщения ядра");
    gtk_list_box_row_set_activatable(GTK_LIST_BOX_ROW(log_act), TRUE);
    g_signal_connect_swapped(log_act, "activated", G_CALLBACK((+[](MainWindow* self) {
        self->show_log_dialog();
    })), this);
    adw_preferences_group_add(diag_group, GTK_WIDGET(log_act));

    AdwActionRow* kernel_act = ADW_ACTION_ROW(adw_action_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(kernel_act), "Управление ядрами");
    adw_action_row_set_subtitle(kernel_act, "Загрузка, обновление и удаление ядер");
    gtk_list_box_row_set_activatable(GTK_LIST_BOX_ROW(kernel_act), TRUE);
    g_signal_connect_swapped(kernel_act, "activated", G_CALLBACK((+[](MainWindow* self) {
        self->show_kernels_dialog();
    })), this);
    adw_preferences_group_add(diag_group, GTK_WIDGET(kernel_act));

    AdwActionRow* data_act = ADW_ACTION_ROW(adw_action_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(data_act), "Каталог данных");
    adw_action_row_set_subtitle(data_act, paths::data_dir().c_str());
    gtk_list_box_row_set_activatable(GTK_LIST_BOX_ROW(data_act), TRUE);
    g_signal_connect_swapped(data_act, "activated", G_CALLBACK((+[](MainWindow* self) {
        std::string cmd = "xdg-open \"" + paths::data_dir().string() + "\" &";
        ::system(cmd.c_str());
    })), this);
    adw_preferences_group_add(diag_group, GTK_WIDGET(data_act));

    adw_preferences_page_add(page, diag_group);

    return GTK_WIDGET(page);
}

void MainWindow::update_latency_label(GtkWidget* label, const std::optional<int>& ms) {
    if (!label) return;
    gtk_widget_remove_css_class(label, "latency-good");
    gtk_widget_remove_css_class(label, "latency-ok");
    gtk_widget_remove_css_class(label, "latency-bad");
    gtk_widget_remove_css_class(label, "latency-unknown");

    if (!ms.has_value()) {
        gtk_label_set_text(GTK_LABEL(label), "—");
        gtk_widget_add_css_class(label, "latency-unknown");
    } else {
        int v = ms.value();
        std::string txt = (v <= 0) ? "<1 мс" : (std::to_string(v) + " мс");
        gtk_label_set_text(GTK_LABEL(label), txt.c_str());
        if (v <= 150) gtk_widget_add_css_class(label, "latency-good");
        else if (v <= 400) gtk_widget_add_css_class(label, "latency-ok");
        else gtk_widget_add_css_class(label, "latency-bad");
    }
}

void MainWindow::update_server_card() {
    auto* p = store_.selected_profile();
    if (!p) {
        gtk_label_set_text(GTK_LABEL(card_flag_), "🌐");
        gtk_label_set_text(GTK_LABEL(card_name_), "Нет профиля");
        gtk_label_set_text(GTK_LABEL(card_addr_), "Добавьте vless:// или подписку");
        gtk_widget_set_visible(card_latency_, FALSE);
        return;
    }

    auto [host, port] = get_host_port(p->uri);
    std::string flag = flags::flag_for(p->name, host);
    gtk_label_set_text(GTK_LABEL(card_flag_), flag.c_str());
    gtk_label_set_text(GTK_LABEL(card_name_), p->name.empty() ? p->uri.c_str() : p->name.c_str());

    std::string addr_str = host.empty() ? "Некорректная ссылка" : (host + ":" + std::to_string(port));
    gtk_label_set_text(GTK_LABEL(card_addr_), addr_str.c_str());

    auto it = latencies_.find(p->id);
    if (it != latencies_.end() && it->second.has_value()) {
        gtk_widget_set_visible(card_latency_, TRUE);
        update_latency_label(card_latency_, it->second);
    } else {
        gtk_widget_set_visible(card_latency_, FALSE);
    }
}

void MainWindow::refresh_all() {
    refresh_ui_status();
    refresh_profiles_list();
    refresh_subscriptions_list();
    update_server_card();

    bool has_items = !store_.profiles.empty() || !store_.subscriptions.empty();
    gtk_widget_set_visible(home_hint_, !has_items);
}

void MainWindow::refresh_ui_status() {
    auto st = core_mgr_.get_status();
    gtk_widget_remove_css_class(big_button_, "connect-idle");
    gtk_widget_remove_css_class(big_button_, "connect-active");
    gtk_widget_remove_css_class(big_button_, "connect-busy");

    std::string mode_str = store_.get_setting("mode", "vpn").get<std::string>();
    std::string mode_label = (mode_str == "vpn") ? "ВПН (TUN)" : ((mode_str == "system") ? "Системный прокси" : "Прокси");

    if (st.state == manager::State::Running) {
        adw_window_title_set_subtitle(ADW_WINDOW_TITLE(header_title_), "Подключено");
        gtk_label_set_text(GTK_LABEL(status_label_), "Подключено");
        auto* prof = store_.get_profile(st.profile_id);
        std::string sub = prof ? (prof->name + " · " + mode_label) : mode_label;
        gtk_label_set_text(GTK_LABEL(detail_label_), sub.c_str());
        gtk_widget_add_css_class(big_button_, "connect-active");
        set_image_icon_with_fallback(GTK_IMAGE(big_icon_), "media-playback-stop-symbolic", 48);
        gtk_widget_set_tooltip_text(big_button_, "Отключиться");

        // Sync sysproxy if mode == system
        if (mode_str == "system") {
            int hp = store_.get_setting("http_port", 10809).get<int>();
            int sp = store_.get_setting("socks_port", 10808).get<int>();
            system::set_sysproxy(true, hp, sp);
        }
    } else if (st.state == manager::State::Starting) {
        adw_window_title_set_subtitle(ADW_WINDOW_TITLE(header_title_), "Подключение…");
        gtk_label_set_text(GTK_LABEL(status_label_), "Подключение…");
        gtk_label_set_text(GTK_LABEL(detail_label_), "Запуск Xray…");
        gtk_widget_add_css_class(big_button_, "connect-busy");
        set_image_icon_with_fallback(GTK_IMAGE(big_icon_), "network-transmit-receive-symbolic", 48);
        gtk_widget_set_tooltip_text(big_button_, "Подключение…");
    } else if (st.state == manager::State::Error) {
        adw_window_title_set_subtitle(ADW_WINDOW_TITLE(header_title_), "Ошибка");
        gtk_label_set_text(GTK_LABEL(status_label_), "Ошибка");
        gtk_label_set_text(GTK_LABEL(detail_label_), st.error.c_str());
        gtk_widget_add_css_class(big_button_, "connect-idle");
        set_image_icon_with_fallback(GTK_IMAGE(big_icon_), "network-vpn-symbolic", 48);
        gtk_widget_set_tooltip_text(big_button_, "Повторить");
        if (mode_str == "system") {
            system::set_sysproxy(false);
        }
    } else {
        adw_window_title_set_subtitle(ADW_WINDOW_TITLE(header_title_), "Отключено");
        gtk_label_set_text(GTK_LABEL(status_label_), "Отключено");
        auto* prof = store_.selected_profile();
        if (prof) {
            gtk_label_set_text(GTK_LABEL(detail_label_), parse_profile_detail(prof->uri).c_str());
        } else {
            gtk_label_set_text(GTK_LABEL(detail_label_), "Выберите профиль или добавьте новый");
        }
        gtk_widget_add_css_class(big_button_, "connect-idle");
        set_image_icon_with_fallback(GTK_IMAGE(big_icon_), "network-vpn-symbolic", 48);
        gtk_widget_set_tooltip_text(big_button_, "Подключиться");
        if (mode_str == "system") {
            system::set_sysproxy(false);
        }
    }
}

void MainWindow::refresh_profiles_list() {
    if (!profiles_list_box_) return;

    // Clear existing
    GtkWidget* child = gtk_widget_get_first_child(profiles_list_box_);
    while (child) {
        GtkWidget* next = gtk_widget_get_next_sibling(child);
        gtk_list_box_remove(GTK_LIST_BOX(profiles_list_box_), child);
        child = next;
    }
    latency_labels_.clear();

    if (store_.profiles.empty()) {
        AdwActionRow* empty_row = ADW_ACTION_ROW(adw_action_row_new());
        adw_preferences_row_set_title(ADW_PREFERENCES_ROW(empty_row), "Профилей пока нет");
        adw_action_row_set_subtitle(empty_row, "Вставьте ссылку vless:// или добавьте подписку");
        gtk_list_box_append(GTK_LIST_BOX(profiles_list_box_), GTK_WIDGET(empty_row));
        return;
    }

    auto profs = store_.profiles;
    bool sort_by_lat = store_.get_setting("sort_by_latency", false).get<bool>();
    if (sort_by_lat) {
        std::sort(profs.begin(), profs.end(), [&](const state::Profile& a, const state::Profile& b) {
            auto it_a = latencies_.find(a.id);
            auto it_b = latencies_.find(b.id);
            int val_a = (it_a != latencies_.end() && it_a->second.has_value()) ? it_a->second.value() : 999999;
            int val_b = (it_b != latencies_.end() && it_b->second.has_value()) ? it_b->second.value() : 999999;
            return val_a < val_b;
        });
    }

    std::string sel_id = store_.get_setting("selected_profile_id", "").get<std::string>();

    for (const auto& prof : profs) {
        AdwActionRow* row = ADW_ACTION_ROW(adw_action_row_new());
        gtk_list_box_row_set_activatable(GTK_LIST_BOX_ROW(row), TRUE);

        std::string title_str = prof.name.empty() ? prof.uri : prof.name;
        std::string sub_str = parse_profile_detail(prof.uri);
        g_autofree gchar* esc_title = g_markup_escape_text(title_str.c_str(), -1);
        g_autofree gchar* esc_subtitle = g_markup_escape_text(sub_str.c_str(), -1);
        adw_preferences_row_set_title(ADW_PREFERENCES_ROW(row), esc_title);
        adw_action_row_set_subtitle(row, esc_subtitle);

        // Checkmark prefix
        GtkWidget* check = gtk_image_new_from_icon_name("object-select-symbolic");
        gtk_widget_set_visible(check, prof.id == sel_id);
        adw_action_row_add_prefix(row, check);

        // Flag prefix
        auto [host, port] = get_host_port(prof.uri);
        std::string flag = flags::flag_for(prof.name, host);
        GtkWidget* flag_lbl = gtk_label_new(flag.c_str());
        gtk_widget_set_margin_start(flag_lbl, 4);
        adw_action_row_add_prefix(row, flag_lbl);

        // Suffix: latency pill + menu
        GtkWidget* suffix_box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6);
        gtk_widget_set_valign(suffix_box, GTK_ALIGN_CENTER);

        GtkWidget* lat_lbl = gtk_label_new("");
        gtk_widget_add_css_class(lat_lbl, "latency-pill");
        auto it = latencies_.find(prof.id);
        update_latency_label(lat_lbl, it != latencies_.end() ? it->second : std::nullopt);
        gtk_box_append(GTK_BOX(suffix_box), lat_lbl);
        latency_labels_[prof.id] = lat_lbl;

        // Context menu
        GMenu* row_menu = g_menu_new();
        g_menu_append(row_menu, "Подключить", ("win.conn-" + prof.id).c_str());
        g_menu_append(row_menu, "Проверить задержку", ("win.ping-" + prof.id).c_str());
        g_menu_append(row_menu, "Переименовать", ("win.ren-" + prof.id).c_str());
        g_menu_append(row_menu, "Удалить", ("win.del-" + prof.id).c_str());

        // Register dynamic actions
        std::string pid = prof.id;
        GSimpleAction* act_c = g_simple_action_new(("conn-" + pid).c_str(), nullptr);
        g_signal_connect_swapped(act_c, "activate", G_CALLBACK((+[](MainWindow* self, gpointer, gpointer, const std::string* id) {
            self->connect_profile(*id);
        })), new std::string(pid));
        g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_c));

        GSimpleAction* act_p = g_simple_action_new(("ping-" + pid).c_str(), nullptr);
        g_signal_connect_swapped(act_p, "activate", G_CALLBACK((+[](MainWindow* self, gpointer, gpointer, const std::string* id) {
            self->ping_profile(*id);
        })), new std::string(pid));
        g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_p));

        GSimpleAction* act_r = g_simple_action_new(("ren-" + pid).c_str(), nullptr);
        g_signal_connect_swapped(act_r, "activate", G_CALLBACK((+[](MainWindow* self, gpointer, gpointer, const std::string* id) {
            self->show_rename_profile_dialog(*id);
        })), new std::string(pid));
        g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_r));

        GSimpleAction* act_d = g_simple_action_new(("del-" + pid).c_str(), nullptr);
        g_signal_connect_swapped(act_d, "activate", G_CALLBACK((+[](MainWindow* self, gpointer, gpointer, const std::string* id) {
            self->show_remove_profile_dialog(*id);
        })), new std::string(pid));
        g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_d));

        GtkWidget* menu_button = gtk_menu_button_new();
        gtk_menu_button_set_icon_name(GTK_MENU_BUTTON(menu_button), "view-more-symbolic");
        gtk_menu_button_set_menu_model(GTK_MENU_BUTTON(menu_button), G_MENU_MODEL(row_menu));
        gtk_widget_add_css_class(menu_button, "flat");
        gtk_box_append(GTK_BOX(suffix_box), menu_button);

        adw_action_row_add_suffix(row, suffix_box);

        // Clicking row selects profile
        std::string* p_id_ptr = new std::string(pid);
        g_signal_connect_swapped(row, "activated", G_CALLBACK((+[](MainWindow* self, const std::string* id) {
            self->select_profile(*id);
        })), p_id_ptr);
        g_object_set_data_full(G_OBJECT(row), "prof_id", p_id_ptr, +[](gpointer d) {
            delete static_cast<std::string*>(d);
        });

        gtk_list_box_append(GTK_LIST_BOX(profiles_list_box_), GTK_WIDGET(row));
    }
}

void MainWindow::refresh_subscriptions_list() {
    if (!subs_list_box_) return;

    GtkWidget* child = gtk_widget_get_first_child(subs_list_box_);
    while (child) {
        GtkWidget* next = gtk_widget_get_next_sibling(child);
        gtk_list_box_remove(GTK_LIST_BOX(subs_list_box_), child);
        child = next;
    }

    if (store_.subscriptions.empty()) {
        AdwActionRow* empty_row = ADW_ACTION_ROW(adw_action_row_new());
        adw_preferences_row_set_title(ADW_PREFERENCES_ROW(empty_row), "Подписок пока нет");
        adw_action_row_set_subtitle(empty_row, "Добавьте URL подписки, чтобы получать профили автоматически");
        gtk_list_box_append(GTK_LIST_BOX(subs_list_box_), GTK_WIDGET(empty_row));
        return;
    }

    for (const auto& sub : store_.subscriptions) {
        AdwActionRow* row = ADW_ACTION_ROW(adw_action_row_new());
        int count = store_.profiles_for_subscription(sub.id).size();

        std::string sub_text = std::to_string(count) + " профилей · обновлено " + format_time(sub.updated_at);
        if (!sub.last_error.empty()) {
            sub_text = std::to_string(count) + " профилей · " + sub.last_error;
        }

        g_autofree gchar* esc_title = g_markup_escape_text(sub.name.c_str(), -1);
        g_autofree gchar* esc_subtitle = g_markup_escape_text(sub_text.c_str(), -1);
        adw_preferences_row_set_title(ADW_PREFERENCES_ROW(row), esc_title);
        adw_action_row_set_subtitle(row, esc_subtitle);

        GtkWidget* icon = gtk_image_new_from_icon_name("view-refresh-symbolic");
        adw_action_row_add_prefix(row, icon);

        GMenu* menu = g_menu_new();
        g_menu_append(menu, "Обновить", ("win.sub-upd-" + sub.id).c_str());
        g_menu_append(menu, "Удалить подписку", ("win.sub-del-" + sub.id).c_str());

        std::string sid = sub.id;
        GSimpleAction* act_u = g_simple_action_new(("sub-upd-" + sid).c_str(), nullptr);
        g_signal_connect_swapped(act_u, "activate", G_CALLBACK((+[](MainWindow* self, gpointer, gpointer, const std::string* id) {
            self->update_subscription(*id);
        })), new std::string(sid));
        g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_u));

        GSimpleAction* act_d = g_simple_action_new(("sub-del-" + sid).c_str(), nullptr);
        g_signal_connect_swapped(act_d, "activate", G_CALLBACK((+[](MainWindow* self, gpointer, gpointer, const std::string* id) {
            self->show_remove_subscription_dialog(*id);
        })), new std::string(sid));
        g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_d));

        GtkWidget* menu_button = gtk_menu_button_new();
        gtk_menu_button_set_icon_name(GTK_MENU_BUTTON(menu_button), "view-more-symbolic");
        gtk_menu_button_set_menu_model(GTK_MENU_BUTTON(menu_button), G_MENU_MODEL(menu));
        gtk_widget_add_css_class(menu_button, "flat");

        adw_action_row_add_suffix(row, menu_button);
        gtk_list_box_append(GTK_LIST_BOX(subs_list_box_), GTK_WIDGET(row));
    }
}

void MainWindow::toggle_connection() {
    auto st = core_mgr_.get_status();
    if (st.state == manager::State::Running || st.state == manager::State::Starting) {
        core_mgr_.stop();
        show_toast("Отключено");
    } else {
        auto* p = store_.selected_profile();
        if (!p) {
            show_toast("Сначала добавьте и выберите профиль");
            return;
        }
        bool tun = store_.get_setting("mode", "vpn").get<std::string>() == "vpn";
        core_mgr_.start(*p, tun);
    }
    refresh_ui_status();
    update_server_card();
}

void MainWindow::select_profile(const std::string& id) {
    store_.select_profile(id);
    refresh_profiles_list();
    update_server_card();
    auto* p = store_.get_profile(id);
    if (p) {
        show_toast("Выбран профиль: " + p->name);
    }
}

void MainWindow::connect_profile(const std::string& id) {
    select_profile(id);
    auto* p = store_.get_profile(id);
    if (p) {
        bool tun = store_.get_setting("mode", "vpn").get<std::string>() == "vpn";
        core_mgr_.start(*p, tun);
        refresh_ui_status();
        update_server_card();
    }
}

void MainWindow::quick_connect() {
    if (!quick_entry_) return;
    std::string text = gtk_editable_get_text(GTK_EDITABLE(quick_entry_));
    if (text.empty()) {
        show_toast("Вставьте ссылку vless:// или URL подписки");
        return;
    }

    if (text.rfind("http://", 0) == 0 || text.rfind("https://", 0) == 0) {
        auto sub = store_.add_subscription(text, text);
        gtk_editable_set_text(GTK_EDITABLE(quick_entry_), "");
        refresh_all();
        show_toast("Подписка добавлена, загружаю профили…");
        update_subscription(sub.id);
        return;
    }

    try {
        std::string name = "Профиль";
        if (text.rfind("hysteria2://", 0) == 0 || text.rfind("hy2://", 0) == 0) {
            name = hysteria::parse_hysteria2(text).name;
        } else {
            name = vless::parse_any_vless(text).name;
        }
        auto p = store_.add_profile(name, text);
        store_.select_profile(p.id);
        gtk_editable_set_text(GTK_EDITABLE(quick_entry_), "");
        refresh_all();
        show_toast("Профиль «" + p.name + "» добавлен");
        bool tun = store_.get_setting("mode", "vpn").get<std::string>() == "vpn";
        core_mgr_.start(p, tun);
    } catch (const std::exception& e) {
        show_toast(std::string("Некорректная ссылка: ") + e.what());
    }
}

void MainWindow::ping_profile(const std::string& id) {
    auto* p = store_.get_profile(id);
    if (!p) return;

    auto [host, port] = get_host_port(p->uri);
    if (host.empty() || port <= 0) return;

    auto it = latency_labels_.find(id);
    if (it != latency_labels_.end() && it->second) {
        gtk_label_set_text(GTK_LABEL(it->second), "…");
    }

    double timeout = store_.get_setting("ping_timeout", 4.0).get<double>();
    std::string ping_type = store_.get_setting("ping_type", "tcp").get<std::string>();

    std::thread([this, id, host, port, ping_type, timeout]() {
        auto res = ping::ping_endpoint(host, port, ping_type, timeout);

        struct PingData {
            MainWindow* self;
            std::string id;
            std::optional<int> ms;
        };
        auto* pd = new PingData{this, id, res};

        g_idle_add(+[](gpointer user_data) -> gboolean {
            auto* data = static_cast<PingData*>(user_data);
            data->self->latencies_[data->id] = data->ms;

            auto it = data->self->latency_labels_.find(data->id);
            if (it != data->self->latency_labels_.end() && it->second) {
                data->self->update_latency_label(it->second, data->ms);
            }

            auto* sel = data->self->store_.selected_profile();
            if (sel && sel->id == data->id) {
                data->self->update_server_card();
            }

            delete data;
            return G_SOURCE_REMOVE;
        }, pd);
    }).detach();
}

void MainWindow::ping_all_profiles() {
    if (store_.profiles.empty()) {
        show_toast("Нет профилей для проверки");
        return;
    }
    show_toast("Проверка задержки всех серверов…");
    for (const auto& p : store_.profiles) {
        ping_profile(p.id);
    }
}

void MainWindow::toggle_sort() {
    bool cur = store_.get_setting("sort_by_latency", false).get<bool>();
    store_.set_setting("sort_by_latency", !cur);
    refresh_profiles_list();
    show_toast(!cur ? "Сортировка по задержке включена" : "Сортировка отключена");
}

void MainWindow::run_speed_test() {
    if (core_mgr_.get_status().state != manager::State::Running) {
        show_toast("Сначала подключитесь — тест идёт через локальный SOCKS5");
        return;
    }
    if (speed_running_) return;

    speed_running_ = true;
    gtk_widget_set_sensitive(speed_button_, FALSE);
    adw_action_row_set_subtitle(ADW_ACTION_ROW(speed_latency_row_), "Измерение…");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(speed_down_row_), "Измерение…");

    int socks_port = store_.get_setting("socks_port", 10808).get<int>();

    std::thread([this, socks_port]() {
        auto res = net::run_speed_test("https://speed.cloudflare.com/__down?bytes=25000000", socks_port, 15);

        struct SpeedCbData {
            MainWindow* self;
            net::SpeedResult res;
        };
        auto* sd = new SpeedCbData{this, res};

        g_idle_add(+[](gpointer p) -> gboolean {
            auto* d = static_cast<SpeedCbData*>(p);
            d->self->speed_running_ = false;
            gtk_widget_set_sensitive(d->self->speed_button_, TRUE);

            if (!d->res.error.empty()) {
                adw_action_row_set_subtitle(ADW_ACTION_ROW(d->self->speed_latency_row_), "—");
                adw_action_row_set_subtitle(ADW_ACTION_ROW(d->self->speed_down_row_), d->res.error.c_str());
            } else {
                int ms = static_cast<int>(d->res.duration * 1000.0);
                adw_action_row_set_subtitle(ADW_ACTION_ROW(d->self->speed_latency_row_), (std::to_string(ms) + " мс").c_str());
                std::ostringstream ss;
                ss.precision(1);
                ss << std::fixed << d->res.mbps << " Мбит/с";
                adw_action_row_set_subtitle(ADW_ACTION_ROW(d->self->speed_down_row_), ss.str().c_str());
            }

            delete d;
            return G_SOURCE_REMOVE;
        }, sd);
    }).detach();
}

void MainWindow::update_subscription(const std::string& id) {
    auto* sub = store_.get_subscription(id);
    if (!sub) return;

    std::string url = sub->url;
    std::string sub_name = sub->name;

    std::thread([this, id, url, sub_name]() {
        auto fetch_res = net::http_get(url, 25);

        struct SubFetchData {
            MainWindow* self;
            std::string id;
            std::string name;
            net::FetchResult fetch;
        };
        auto* sfd = new SubFetchData{this, id, sub_name, fetch_res};

        g_idle_add(+[](gpointer p) -> gboolean {
            auto* d = static_cast<SubFetchData*>(p);
            if (!d->fetch.success) {
                d->self->store_.set_subscription_error(d->id, d->fetch.error);
                d->self->show_toast("Ошибка обновления «" + d->name + "»: " + d->fetch.error);
            } else {
                auto entries = net::parse_subscription_payload(d->fetch.data);
                int count = d->self->store_.replace_subscription_profiles(d->id, entries);
                d->self->show_toast("«" + d->name + "»: обновлено " + std::to_string(count) + " профилей");
            }
            d->self->refresh_all();
            delete d;
            return G_SOURCE_REMOVE;
        }, sfd);
    }).detach();
}

void MainWindow::update_all_subscriptions() {
    if (store_.subscriptions.empty()) {
        show_toast("Подписок пока нет");
        return;
    }
    show_toast("Обновление всех подписок…");
    for (const auto& s : store_.subscriptions) {
        update_subscription(s.id);
    }
}

// Dialogs
void MainWindow::show_kernels_dialog() {
    show_dialog_kernels(window_, store_, &core_mgr_, [this](const std::string& m) {
        show_toast(m);
    });
}

void MainWindow::show_about_dialog() {
    adw_show_about_dialog(
        window_,
        "application-name", paths::APP_TITLE.c_str(),
        "application-icon", "network-vpn-symbolic",
        "developer-name", "Dma2ray contributors",
        "version", paths::VERSION.c_str(),
        "comments", "Сверхбыстрый нативный C++ Xray & Hysteria2 GUI клиент для Linux на GTK4/libadwaita.",
        "website", "https://github.com/XTLS/Xray-core",
        nullptr
    );
}

void MainWindow::show_log_dialog() {
    AdwDialog* dialog = adw_dialog_new();
    adw_dialog_set_title(dialog, "Журнал Xray");
    adw_dialog_set_content_width(dialog, 760);
    adw_dialog_set_content_height(dialog, 560);

    AdwToolbarView* toolbar = ADW_TOOLBAR_VIEW(adw_toolbar_view_new());
    AdwHeaderBar* header = ADW_HEADER_BAR(adw_header_bar_new());
    adw_header_bar_set_title_widget(header, adw_window_title_new("Журнал Xray", paths::log_file().c_str()));

    GtkWidget* refresh_btn = gtk_button_new_from_icon_name("view-refresh-symbolic");
    gtk_widget_add_css_class(refresh_btn, "flat");
    gtk_widget_set_tooltip_text(refresh_btn, "Обновить");
    adw_header_bar_pack_end(header, refresh_btn);
    adw_toolbar_view_add_top_bar(toolbar, GTK_WIDGET(header));

    GtkWidget* scrl = gtk_scrolled_window_new();
    gtk_widget_set_vexpand(scrl, TRUE);

    GtkWidget* tv = gtk_text_view_new();
    gtk_text_view_set_editable(GTK_TEXT_VIEW(tv), FALSE);
    gtk_text_view_set_cursor_visible(GTK_TEXT_VIEW(tv), FALSE);
    gtk_text_view_set_monospace(GTK_TEXT_VIEW(tv), TRUE);
    gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(tv), GTK_WRAP_WORD_CHAR);
    gtk_widget_set_margin_start(tv, 12);
    gtk_widget_set_margin_end(tv, 12);
    gtk_widget_set_margin_top(tv, 8);
    gtk_widget_set_margin_bottom(tv, 8);

    GtkTextBuffer* buf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(tv));

    auto update_fn = [tv, buf]() {
        std::string content = "Журнал пока пуст.";
        if (std::filesystem::exists(paths::log_file())) {
            std::ifstream f(paths::log_file());
            std::string line, all;
            while (std::getline(f, line)) all += line + "\n";
            if (!all.empty()) content = all;
        }
        gtk_text_buffer_set_text(buf, content.c_str(), -1);
        GtkTextIter end;
        gtk_text_buffer_get_end_iter(buf, &end);
        gtk_text_view_scroll_to_iter(GTK_TEXT_VIEW(tv), &end, 0.0, FALSE, 0.0, 0.0);
    };

    update_fn();
    g_signal_connect_swapped(refresh_btn, "clicked", G_CALLBACK((+[](MainWindow* self) {
        // Refresh log
    })), this);

    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scrl), tv);
    adw_toolbar_view_set_content(toolbar, scrl);
    adw_dialog_set_child(dialog, GTK_WIDGET(toolbar));
    adw_dialog_present(dialog, window_);
}

void MainWindow::show_add_profile_dialog() {
    AdwDialog* dialog = adw_dialog_new();
    adw_dialog_set_title(dialog, "Новый профиль");
    adw_dialog_set_content_width(dialog, 480);

    AdwToolbarView* toolbar = ADW_TOOLBAR_VIEW(adw_toolbar_view_new());
    AdwHeaderBar* header = ADW_HEADER_BAR(adw_header_bar_new());
    adw_header_bar_set_title_widget(header, adw_window_title_new("Новый профиль", "Импорт vless:// или hysteria2://"));

    GtkWidget* cancel_btn = gtk_button_new_with_label("Отмена");
    g_signal_connect_swapped(cancel_btn, "clicked", G_CALLBACK((+[](AdwDialog* d) {
        adw_dialog_close(d);
    })), dialog);
    adw_header_bar_pack_start(header, cancel_btn);

    GtkWidget* add_btn = gtk_button_new_with_label("Добавить");
    gtk_widget_add_css_class(add_btn, "suggested-action");
    gtk_widget_set_sensitive(add_btn, FALSE);
    adw_header_bar_pack_end(header, add_btn);
    adw_toolbar_view_add_top_bar(toolbar, GTK_WIDGET(header));

    AdwPreferencesPage* page = ADW_PREFERENCES_PAGE(adw_preferences_page_new());
    AdwPreferencesGroup* grp = ADW_PREFERENCES_GROUP(adw_preferences_group_new());
    adw_preferences_group_set_title(grp, "Ссылка");
    adw_preferences_group_set_description(grp, "Вставьте ссылку vless:// или hysteria2://");

    AdwEntryRow* link_row = ADW_ENTRY_ROW(adw_entry_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(link_row), "vless://…");
    adw_preferences_group_add(grp, GTK_WIDGET(link_row));

    AdwEntryRow* name_row = ADW_ENTRY_ROW(adw_entry_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(name_row), "Название (необязательно)");
    adw_preferences_group_add(grp, GTK_WIDGET(name_row));

    AdwActionRow* preview_row = ADW_ACTION_ROW(adw_action_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(preview_row), "Предпросмотр");
    adw_action_row_set_subtitle(preview_row, "—");
    adw_preferences_group_add(grp, GTK_WIDGET(preview_row));

    adw_preferences_page_add(page, grp);
    adw_toolbar_view_set_content(toolbar, GTK_WIDGET(page));
    adw_dialog_set_child(dialog, GTK_WIDGET(toolbar));

    struct AddProfileCtx {
        MainWindow* self;
        AdwDialog* dialog;
        AdwEntryRow* link_row;
        AdwEntryRow* name_row;
        AdwActionRow* preview_row;
        GtkWidget* add_btn;
    };
    auto* ctx = new AddProfileCtx{this, dialog, link_row, name_row, preview_row, add_btn};

    g_signal_connect_swapped(link_row, "notify::text", G_CALLBACK((+[](AddProfileCtx* c) {
        std::string uri = gtk_editable_get_text(GTK_EDITABLE(c->link_row));
        if (uri.empty()) {
            adw_action_row_set_subtitle(c->preview_row, "—");
            gtk_widget_set_sensitive(c->add_btn, FALSE);
            return;
        }
        std::string detail = parse_profile_detail(uri);
        adw_action_row_set_subtitle(c->preview_row, detail.c_str());
        bool valid = (detail != "Некорректная ссылка");
        gtk_widget_set_sensitive(c->add_btn, valid);
    })), ctx);

    auto on_add = +[](AddProfileCtx* c) {
        std::string uri = gtk_editable_get_text(GTK_EDITABLE(c->link_row));
        std::string custom_name = gtk_editable_get_text(GTK_EDITABLE(c->name_row));
        if (uri.empty()) return;

        std::string default_name = "Профиль";
        try {
            if (uri.rfind("hysteria2://", 0) == 0 || uri.rfind("hy2://", 0) == 0) {
                default_name = hysteria::parse_hysteria2(uri).name;
            } else {
                default_name = vless::parse_any_vless(uri).name;
            }
        } catch (...) {}

        std::string final_name = custom_name.empty() ? default_name : custom_name;
        auto p = c->self->store_.add_profile(final_name, uri);
        c->self->store_.select_profile(p.id);
        c->self->refresh_all();
        c->self->show_toast("Профиль «" + p.name + "» добавлен");
        adw_dialog_close(c->dialog);
    };

    g_signal_connect_swapped(add_btn, "clicked", G_CALLBACK(on_add), ctx);
    g_signal_connect_swapped(link_row, "entry-activated", G_CALLBACK(on_add), ctx);

    g_object_set_data_full(G_OBJECT(dialog), "ctx", ctx, +[](gpointer d) {
        delete static_cast<AddProfileCtx*>(d);
    });

    adw_dialog_present(dialog, window_);
}

void MainWindow::show_add_subscription_dialog() {
    AdwDialog* dialog = adw_dialog_new();
    adw_dialog_set_title(dialog, "Новая подписка");
    adw_dialog_set_content_width(dialog, 480);

    AdwToolbarView* toolbar = ADW_TOOLBAR_VIEW(adw_toolbar_view_new());
    AdwHeaderBar* header = ADW_HEADER_BAR(adw_header_bar_new());
    adw_header_bar_set_title_widget(header, adw_window_title_new("Новая подписка", "URL со списком vless://"));

    GtkWidget* cancel_btn = gtk_button_new_with_label("Отмена");
    g_signal_connect_swapped(cancel_btn, "clicked", G_CALLBACK((+[](AdwDialog* d) {
        adw_dialog_close(d);
    })), dialog);
    adw_header_bar_pack_start(header, cancel_btn);

    GtkWidget* add_btn = gtk_button_new_with_label("Добавить");
    gtk_widget_add_css_class(add_btn, "suggested-action");
    gtk_widget_set_sensitive(add_btn, FALSE);
    adw_header_bar_pack_end(header, add_btn);
    adw_toolbar_view_add_top_bar(toolbar, GTK_WIDGET(header));

    AdwPreferencesPage* page = ADW_PREFERENCES_PAGE(adw_preferences_page_new());
    AdwPreferencesGroup* grp = ADW_PREFERENCES_GROUP(adw_preferences_group_new());

    AdwEntryRow* name_row = ADW_ENTRY_ROW(adw_entry_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(name_row), "Название");
    adw_preferences_group_add(grp, GTK_WIDGET(name_row));

    AdwEntryRow* url_row = ADW_ENTRY_ROW(adw_entry_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(url_row), "URL подписки");
    adw_preferences_group_add(grp, GTK_WIDGET(url_row));

    adw_preferences_page_add(page, grp);
    adw_toolbar_view_set_content(toolbar, GTK_WIDGET(page));
    adw_dialog_set_child(dialog, GTK_WIDGET(toolbar));

    struct AddSubCtx {
        MainWindow* self;
        AdwDialog* dialog;
        AdwEntryRow* name_row;
        AdwEntryRow* url_row;
        GtkWidget* add_btn;
    };
    auto* ctx = new AddSubCtx{this, dialog, name_row, url_row, add_btn};

    g_signal_connect_swapped(url_row, "notify::text", G_CALLBACK((+[](AddSubCtx* c) {
        std::string url = gtk_editable_get_text(GTK_EDITABLE(c->url_row));
        bool ok = (url.rfind("http://", 0) == 0 || url.rfind("https://", 0) == 0);
        gtk_widget_set_sensitive(c->add_btn, ok);
    })), ctx);

    auto on_add = +[](AddSubCtx* c) {
        std::string url = gtk_editable_get_text(GTK_EDITABLE(c->url_row));
        std::string name = gtk_editable_get_text(GTK_EDITABLE(c->name_row));
        if (url.empty()) return;
        if (name.empty()) name = url;

        auto sub = c->self->store_.add_subscription(name, url);
        c->self->refresh_all();
        c->self->show_toast("Подписка добавлена, загружаю профили…");
        c->self->update_subscription(sub.id);
        adw_dialog_close(c->dialog);
    };

    g_signal_connect_swapped(add_btn, "clicked", G_CALLBACK(on_add), ctx);
    g_signal_connect_swapped(url_row, "entry-activated", G_CALLBACK(on_add), ctx);

    g_object_set_data_full(G_OBJECT(dialog), "ctx", ctx, +[](gpointer d) {
        delete static_cast<AddSubCtx*>(d);
    });

    adw_dialog_present(dialog, window_);
}

void MainWindow::show_rename_profile_dialog(const std::string& id) {
    auto* prof = store_.get_profile(id);
    if (!prof) return;

    AdwAlertDialog* alert = ADW_ALERT_DIALOG(adw_alert_dialog_new("Переименовать профиль", "Введите новое название:"));
    GtkWidget* entry = gtk_entry_new();
    gtk_editable_set_text(GTK_EDITABLE(entry), prof->name.c_str());
    adw_alert_dialog_set_extra_child(alert, entry);

    adw_alert_dialog_add_response(alert, "cancel", "Отмена");
    adw_alert_dialog_add_response(alert, "save", "Сохранить");
    adw_alert_dialog_set_response_appearance(alert, "save", ADW_RESPONSE_SUGGESTED);
    adw_alert_dialog_set_default_response(alert, "save");
    adw_alert_dialog_set_close_response(alert, "cancel");

    struct RenData {
        MainWindow* self;
        std::string id;
        GtkWidget* entry;
    };
    auto* rd = new RenData{this, id, entry};

    adw_alert_dialog_choose(alert, window_, nullptr, +[](GObject* src, GAsyncResult* res, gpointer user_data) {
        auto* d = static_cast<RenData*>(user_data);
        const char* resp = adw_alert_dialog_choose_finish(ADW_ALERT_DIALOG(src), res);
        if (resp && std::string(resp) == "save") {
            std::string new_name = gtk_editable_get_text(GTK_EDITABLE(d->entry));
            if (!new_name.empty()) {
                d->self->store_.rename_profile(d->id, new_name);
                d->self->refresh_all();
            }
        }
        delete d;
    }, rd);
}

void MainWindow::show_remove_profile_dialog(const std::string& id) {
    auto* prof = store_.get_profile(id);
    if (!prof) return;

    std::string heading = "Удалить профиль?";
    std::string body = "«" + prof->name + "» будет удалён.";
    AdwAlertDialog* alert = ADW_ALERT_DIALOG(adw_alert_dialog_new(heading.c_str(), body.c_str()));
    adw_alert_dialog_add_response(alert, "cancel", "Отмена");
    adw_alert_dialog_add_response(alert, "delete", "Удалить");
    adw_alert_dialog_set_response_appearance(alert, "delete", ADW_RESPONSE_DESTRUCTIVE);
    adw_alert_dialog_set_default_response(alert, "cancel");
    adw_alert_dialog_set_close_response(alert, "cancel");

    struct DelData {
        MainWindow* self;
        std::string id;
    };
    auto* dd = new DelData{this, id};

    adw_alert_dialog_choose(alert, window_, nullptr, +[](GObject* src, GAsyncResult* res, gpointer user_data) {
        auto* d = static_cast<DelData*>(user_data);
        const char* resp = adw_alert_dialog_choose_finish(ADW_ALERT_DIALOG(src), res);
        if (resp && std::string(resp) == "delete") {
            if (d->self->core_mgr_.get_status().profile_id == d->id) {
                d->self->core_mgr_.stop();
            }
            d->self->store_.remove_profile(d->id);
            d->self->refresh_all();
            d->self->show_toast("Профиль удалён");
        }
        delete d;
    }, dd);
}

void MainWindow::show_remove_subscription_dialog(const std::string& id) {
    auto* sub = store_.get_subscription(id);
    if (!sub) return;

    std::string heading = "Удалить подписку?";
    std::string body = "«" + sub->name + "» и все её профили будут удалены.";
    AdwAlertDialog* alert = ADW_ALERT_DIALOG(adw_alert_dialog_new(heading.c_str(), body.c_str()));
    adw_alert_dialog_add_response(alert, "cancel", "Отмена");
    adw_alert_dialog_add_response(alert, "delete", "Удалить");
    adw_alert_dialog_set_response_appearance(alert, "delete", ADW_RESPONSE_DESTRUCTIVE);
    adw_alert_dialog_set_default_response(alert, "cancel");
    adw_alert_dialog_set_close_response(alert, "cancel");

    struct DelSubData {
        MainWindow* self;
        std::string id;
    };
    auto* dd = new DelSubData{this, id};

    adw_alert_dialog_choose(alert, window_, nullptr, +[](GObject* src, GAsyncResult* res, gpointer user_data) {
        auto* d = static_cast<DelSubData*>(user_data);
        const char* resp = adw_alert_dialog_choose_finish(ADW_ALERT_DIALOG(src), res);
        if (resp && std::string(resp) == "delete") {
            d->self->store_.remove_subscription(d->id);
            d->self->refresh_all();
            d->self->show_toast("Подписка удалена");
        }
        delete d;
    }, dd);
}

} // namespace dma2ray::ui
