#include "dma2ray/window.hpp"
#include "dma2ray/paths.hpp"
#include "dma2ray/theme.hpp"
#include <fstream>

namespace dma2ray::ui {

MainWindow::MainWindow(AdwApplication* app, state::Store& store, manager::CoreManager& core_mgr)
    : app_(app), store_(store), core_mgr_(core_mgr) {
    build_ui();
}

void MainWindow::present() {
    if (window_) gtk_window_present(GTK_WINDOW(window_));
}

void MainWindow::build_ui() {
    window_ = adw_application_window_new(GTK_APPLICATION(app_));
    gtk_window_set_title(GTK_WINDOW(window_), paths::APP_TITLE.c_str());
    gtk_window_set_default_size(GTK_WINDOW(window_), 440, 800);

    toast_overlay_ = adw_toast_overlay_new();

    AdwToolbarView* toolbar = ADW_TOOLBAR_VIEW(adw_toolbar_view_new());
    AdwHeaderBar* header = ADW_HEADER_BAR(adw_header_bar_new());
    gtk_widget_add_css_class(GTK_WIDGET(header), "main-headerbar");

    GtkWidget* title = adw_window_title_new(paths::APP_TITLE.c_str(), "Xray & Hysteria2 GUI");
    adw_header_bar_set_title_widget(header, title);

    GMenu* menu = g_menu_new();
    g_menu_append(menu, "Ядра", "win.kernels");
    g_menu_append(menu, "Журнал Xray", "win.show-log");
    g_menu_append(menu, "О программе", "win.about");

    GtkWidget* menu_btn = gtk_menu_button_new();
    gtk_menu_button_set_icon_name(GTK_MENU_BUTTON(menu_btn), "open-menu-symbolic");
    gtk_menu_button_set_menu_model(GTK_MENU_BUTTON(menu_btn), G_MENU_MODEL(menu));
    adw_header_bar_pack_end(header, menu_btn);
    adw_toolbar_view_add_top_bar(toolbar, GTK_WIDGET(header));

    view_stack_ = adw_view_stack_new();
    gtk_widget_set_vexpand(view_stack_, TRUE);

    GtkWidget* home_page = build_home_page();
    adw_view_stack_add_titled(ADW_VIEW_STACK(view_stack_), home_page, "home", "Главная");

    GtkWidget* servers_page = build_servers_page();
    adw_view_stack_add_titled(ADW_VIEW_STACK(view_stack_), servers_page, "servers", "Серверы");

    GtkWidget* settings_page = build_settings_page();
    adw_view_stack_add_titled(ADW_VIEW_STACK(view_stack_), settings_page, "settings", "Настройки");

    AdwViewSwitcherBar* switcher_bar = ADW_VIEW_SWITCHER_BAR(adw_view_switcher_bar_new());
    adw_view_switcher_bar_set_stack(switcher_bar, ADW_VIEW_STACK(view_stack_));
    adw_view_switcher_bar_set_reveal(switcher_bar, TRUE);
    gtk_widget_add_css_class(GTK_WIDGET(switcher_bar), "main-switcherbar");

    adw_toolbar_view_add_bottom_bar(toolbar, GTK_WIDGET(switcher_bar));
    adw_toolbar_view_set_content(toolbar, view_stack_);

    adw_toast_overlay_set_child(ADW_TOAST_OVERLAY(toast_overlay_), GTK_WIDGET(toolbar));
    adw_application_window_set_content(ADW_APPLICATION_WINDOW(window_), toast_overlay_);

    // Actions
    GSimpleAction* act_kernels = g_simple_action_new("kernels", nullptr);
    g_signal_connect_swapped(act_kernels, "activate", G_CALLBACK(+[](MainWindow* self) {
        self->show_kernels_dialog();
    }), this);
    g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_kernels));

    GSimpleAction* act_about = g_simple_action_new("about", nullptr);
    g_signal_connect_swapped(act_about, "activate", G_CALLBACK(+[](MainWindow* self) {
        self->show_about_dialog();
    }), this);
    g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_about));

    GSimpleAction* act_log = g_simple_action_new("show-log", nullptr);
    g_signal_connect_swapped(act_log, "activate", G_CALLBACK(+[](MainWindow* self) {
        self->show_log_dialog();
    }), this);
    g_action_map_add_action(G_ACTION_MAP(window_), G_ACTION(act_log));

    refresh_ui_status();
    refresh_profiles_list();
}

GtkWidget* MainWindow::build_home_page() {
    GtkWidget* scrolled = gtk_scrolled_window_new();
    GtkWidget* clamp = adw_clamp_new();
    adw_clamp_set_maximum_size(ADW_CLAMP(clamp), 540);

    GtkWidget* box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 16);
    gtk_widget_set_margin_start(box, 18);
    gtk_widget_set_margin_end(box, 18);
    gtk_widget_set_margin_top(box, 24);
    gtk_widget_set_margin_bottom(box, 24);

    status_label_ = gtk_label_new("Отключено");
    gtk_widget_add_css_class(status_label_, "home-status");
    gtk_box_append(GTK_BOX(box), status_label_);

    detail_label_ = gtk_label_new("Выберите профиль");
    gtk_widget_add_css_class(detail_label_, "section-hint");
    gtk_box_append(GTK_BOX(box), detail_label_);

    big_icon_ = gtk_image_new_from_icon_name("network-vpn-symbolic");
    gtk_image_set_pixel_size(GTK_IMAGE(big_icon_), 48);

    big_button_ = gtk_button_new();
    gtk_button_set_child(GTK_BUTTON(big_button_), big_icon_);
    gtk_widget_add_css_class(big_button_, "connect-big");
    gtk_widget_add_css_class(big_button_, "connect-idle");
    gtk_widget_set_halign(big_button_, GTK_ALIGN_CENTER);

    g_signal_connect_swapped(big_button_, "clicked", G_CALLBACK(+[](MainWindow* self) {
        self->toggle_connection();
    }), this);
    gtk_box_append(GTK_BOX(box), big_button_);

    // Server card
    GtkWidget* card_btn = gtk_button_new();
    gtk_widget_add_css_class(card_btn, "flat");
    gtk_widget_add_css_class(card_btn, "server-card");
    g_signal_connect_swapped(card_btn, "clicked", G_CALLBACK(+[](MainWindow* self) {
        adw_view_stack_set_visible_child_name(ADW_VIEW_STACK(self->view_stack_), "servers");
    }), this);

    GtkWidget* card_box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    GtkWidget* flag = gtk_label_new("🌐");
    gtk_widget_add_css_class(flag, "flag-big");
    gtk_box_append(GTK_BOX(card_box), flag);

    GtkWidget* text_box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 2);
    gtk_widget_set_hexpand(text_box, TRUE);
    card_name_ = gtk_label_new("Нет профиля");
    gtk_label_set_xalign(GTK_LABEL(card_name_), 0.0f);
    gtk_widget_add_css_class(card_name_, "heading");
    gtk_box_append(GTK_BOX(text_box), card_name_);

    card_addr_ = gtk_label_new("Добавьте vless:// или подписку");
    gtk_label_set_xalign(GTK_LABEL(card_addr_), 0.0f);
    gtk_widget_add_css_class(card_addr_, "section-hint");
    gtk_box_append(GTK_BOX(text_box), card_addr_);
    gtk_box_append(GTK_BOX(card_box), text_box);

    card_latency_ = gtk_label_new("");
    gtk_widget_add_css_class(card_latency_, "latency-pill");
    gtk_widget_set_visible(card_latency_, FALSE);
    gtk_box_append(GTK_BOX(card_box), card_latency_);

    GtkWidget* next_icon = gtk_image_new_from_icon_name("go-next-symbolic");
    gtk_box_append(GTK_BOX(card_box), next_icon);

    gtk_button_set_child(GTK_BUTTON(card_btn), card_box);
    gtk_box_append(GTK_BOX(box), card_btn);

    adw_clamp_set_child(ADW_CLAMP(clamp), box);
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scrolled), clamp);
    return scrolled;
}

GtkWidget* MainWindow::build_servers_page() {
    GtkWidget* scrolled = gtk_scrolled_window_new();
    GtkWidget* clamp = adw_clamp_new();
    adw_clamp_set_maximum_size(ADW_CLAMP(clamp), 540);

    GtkWidget* box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 16);
    gtk_widget_set_margin_start(box, 18);
    gtk_widget_set_margin_end(box, 18);
    gtk_widget_set_margin_top(box, 18);
    gtk_widget_set_margin_bottom(box, 18);

    profiles_list_box_ = gtk_list_box_new();
    gtk_widget_add_css_class(profiles_list_box_, "boxed-list");
    gtk_box_append(GTK_BOX(box), profiles_list_box_);

    adw_clamp_set_child(ADW_CLAMP(clamp), box);
    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scrolled), clamp);
    return scrolled;
}

GtkWidget* MainWindow::build_settings_page() {
    AdwPreferencesPage* page = ADW_PREFERENCES_PAGE(adw_preferences_page_new());

    AdwPreferencesGroup* group_mode = ADW_PREFERENCES_GROUP(adw_preferences_group_new());
    adw_preferences_group_set_title(group_mode, "Режим работы");

    const char* modes[] = {"Прокси (SOCKS5/HTTP)", "Системный прокси", "ВПН (TUN, нужен root)", nullptr};
    AdwComboRow* mode_row = ADW_COMBO_ROW(adw_combo_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(mode_row), "Режим сети");
    adw_combo_row_set_model(mode_row, G_LIST_MODEL(gtk_string_list_new(modes)));
    adw_preferences_group_add(group_mode, GTK_WIDGET(mode_row));
    adw_preferences_page_add(page, group_mode);

    AdwPreferencesGroup* group_core = ADW_PREFERENCES_GROUP(adw_preferences_group_new());
    adw_preferences_group_set_title(group_core, "Ядро");
    AdwActionRow* core_row = ADW_ACTION_ROW(adw_action_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(core_row), "Управление ядрами");
    adw_action_row_set_subtitle(core_row, "Скачивание и выбор активного ядра");
    GtkWidget* open_cores_btn = gtk_button_new_with_label("Открыть");
    gtk_widget_set_valign(open_cores_btn, GTK_ALIGN_CENTER);
    g_signal_connect_swapped(open_cores_btn, "clicked", G_CALLBACK(+[](MainWindow* self) {
        self->show_kernels_dialog();
    }), this);
    adw_action_row_add_suffix(core_row, open_cores_btn);
    adw_preferences_group_add(group_core, GTK_WIDGET(core_row));
    adw_preferences_page_add(page, group_core);

    return GTK_WIDGET(page);
}

void MainWindow::show_kernels_dialog() {
    show_dialog_kernels(window_, store_);
}

void MainWindow::show_about_dialog() {
    adw_show_about_dialog(
        window_,
        "application-name", paths::APP_TITLE.c_str(),
        "application-icon", "network-vpn-symbolic",
        "developer-name", "Dma2ray contributors",
        "version", paths::VERSION.c_str(),
        "comments", "Сверхбыстрый нативный C++ Xray & Hysteria2 GUI клиент",
        nullptr
    );
}

void MainWindow::show_log_dialog() {
    AdwDialog* dialog = adw_dialog_new();
    adw_dialog_set_title(dialog, "Журнал Xray");
    adw_dialog_set_content_width(dialog, 700);
    adw_dialog_set_content_height(dialog, 500);

    GtkWidget* scrl = gtk_scrolled_window_new();
    GtkWidget* tv = gtk_text_view_new();
    gtk_text_view_set_editable(GTK_TEXT_VIEW(tv), FALSE);
    gtk_text_view_set_monospace(GTK_TEXT_VIEW(tv), TRUE);

    GtkTextBuffer* buf = gtk_text_view_get_buffer(GTK_TEXT_VIEW(tv));
    std::string content = "Журнал пока пуст.";
    if (std::filesystem::exists(paths::log_file())) {
        std::ifstream f(paths::log_file());
        std::string line, all;
        while (std::getline(f, line)) all += line + "\n";
        if (!all.empty()) content = all;
    }
    gtk_text_buffer_set_text(buf, content.c_str(), -1);

    gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scrl), tv);
    adw_dialog_set_child(dialog, scrl);
    adw_dialog_present(dialog, window_);
}

void MainWindow::toggle_connection() {
    auto st = core_mgr_.get_status();
    if (st.state == manager::State::Running || st.state == manager::State::Starting) {
        core_mgr_.stop();
    } else {
        std::string sel_id = store_.get_setting("selected_profile_id", "").get<std::string>();
        auto* p = store_.get_profile(sel_id);
        if (!p && !store_.profiles.empty()) p = &store_.profiles.front();
        if (p) {
            bool tun = store_.get_setting("mode", "vpn").get<std::string>() == "vpn";
            core_mgr_.start(*p, tun);
        }
    }
    refresh_ui_status();
}

void MainWindow::refresh_ui_status() {
    auto st = core_mgr_.get_status();
    gtk_widget_remove_css_class(big_button_, "connect-idle");
    gtk_widget_remove_css_class(big_button_, "connect-active");
    gtk_widget_remove_css_class(big_button_, "connect-busy");

    if (st.state == manager::State::Running) {
        gtk_label_set_text(GTK_LABEL(status_label_), "Подключено");
        gtk_widget_add_css_class(big_button_, "connect-active");
    } else if (st.state == manager::State::Starting) {
        gtk_label_set_text(GTK_LABEL(status_label_), "Подключение...");
        gtk_widget_add_css_class(big_button_, "connect-busy");
    } else if (st.state == manager::State::Error) {
        gtk_label_set_text(GTK_LABEL(status_label_), "Ошибка подключения");
        gtk_label_set_text(GTK_LABEL(detail_label_), st.error.c_str());
        gtk_widget_add_css_class(big_button_, "connect-idle");
    } else {
        gtk_label_set_text(GTK_LABEL(status_label_), "Отключено");
        gtk_widget_add_css_class(big_button_, "connect-idle");
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

    std::string sel_id = store_.get_setting("selected_profile_id", "").get<std::string>();

    for (const auto& prof : store_.profiles) {
        AdwActionRow* row = ADW_ACTION_ROW(adw_action_row_new());
        adw_preferences_row_set_title(ADW_PREFERENCES_ROW(row), prof.name.empty() ? prof.uri.c_str() : prof.name.c_str());
        adw_action_row_set_subtitle(row, prof.uri.c_str());

        GtkWidget* check = gtk_image_new_from_icon_name("object-select-symbolic");
        gtk_widget_set_visible(check, prof.id == sel_id);
        adw_action_row_add_suffix(row, check);

        gtk_list_box_append(GTK_LIST_BOX(profiles_list_box_), GTK_WIDGET(row));
    }
}

} // namespace dma2ray::ui
