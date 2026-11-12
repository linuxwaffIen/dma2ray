#include "dma2ray/window.hpp"
#include "dma2ray/paths.hpp"
#include "dma2ray/installer.hpp"

#include <filesystem>

namespace dma2ray::ui {

void show_dialog_kernels(GtkWidget* parent, state::Store& store) {
    AdwDialog* dialog = adw_dialog_new();
    adw_dialog_set_title(dialog, "Ядра");
    adw_dialog_set_presentation_mode(dialog, ADW_DIALOG_BOTTOM_SHEET);
    adw_dialog_set_content_width(dialog, 480);
    adw_dialog_set_content_height(dialog, 520);

    AdwToolbarView* toolbar = ADW_TOOLBAR_VIEW(adw_toolbar_view_new());
    AdwHeaderBar* header = ADW_HEADER_BAR(adw_header_bar_new());
    std::string title_sub = paths::current_arch() + " · v" + paths::VERSION;
    adw_header_bar_set_title_widget(header, adw_window_title_new("Ядра", title_sub.c_str()));
    adw_toolbar_view_add_top_bar(toolbar, GTK_WIDGET(header));

    AdwPreferencesPage* page = ADW_PREFERENCES_PAGE(adw_preferences_page_new());

    AdwPreferencesGroup* mode_group = ADW_PREFERENCES_GROUP(adw_preferences_group_new());
    adw_preferences_group_set_title(mode_group, "Выбор ядра");
    const char* modes[] = {"Автовыбор (по протоколу)", "Xray-core", "Amnezia Xray", nullptr};
    GtkStringList* mode_list = gtk_string_list_new(modes);
    AdwComboRow* mode_row = ADW_COMBO_ROW(adw_combo_row_new());
    adw_preferences_row_set_title(ADW_PREFERENCES_ROW(mode_row), "Активное ядро");
    adw_action_row_set_subtitle(ADW_ACTION_ROW(mode_row), "Автовыбор подбирает ядро под протокол профиля");
    adw_combo_row_set_model(mode_row, G_LIST_MODEL(mode_list));
    
    std::string current_km = store.get_setting("kernel_mode", "auto").get<std::string>();
    guint sel_idx = 0;
    if (current_km == "xray") sel_idx = 1;
    else if (current_km == "amnezia-xray") sel_idx = 2;
    adw_combo_row_set_selected(mode_row, sel_idx);

    g_signal_connect_swapped(mode_row, "notify::selected", G_CALLBACK(+[](state::Store* s, AdwComboRow* row) {
        guint sel = adw_combo_row_get_selected(row);
        const char* km = "auto";
        if (sel == 1) km = "xray";
        else if (sel == 2) km = "amnezia-xray";
        s->set_setting("kernel_mode", km);
    }), &store);

    adw_preferences_group_add(mode_group, GTK_WIDGET(mode_row));
    adw_preferences_page_add(page, mode_group);

    AdwPreferencesGroup* group = ADW_PREFERENCES_GROUP(adw_preferences_group_new());
    adw_preferences_group_set_title(group, "Доступные ядра");
    adw_preferences_group_set_description(group, "Загрузка для вашей архитектуры. Новое ядро применится при следующем подключении.");

    struct KernelItem {
        const char* type;
        const char* title;
        const char* subtitle;
        const char* icon;
    } items[] = {
        {"xray", "Xray-core", "Официальное ядро XTLS", "applications-system-symbolic"},
        {"amnezia-xray", "Amnezia Xray", "Сборка Xray от Amnezia", "security-high-symbolic"},
        {"hysteria", "Hysteria 2", "QUIC-прокси от apernet", "network-wireless-symbolic"}
    };

    for (const auto& item : items) {
        AdwActionRow* row = ADW_ACTION_ROW(adw_action_row_new());
        adw_preferences_row_set_title(ADW_PREFERENCES_ROW(row), item.title);
        adw_action_row_set_subtitle(row, item.subtitle);

        GtkWidget* icon = gtk_image_new_from_icon_name(item.icon);
        gtk_widget_add_css_class(icon, "kernel-icon");
        adw_action_row_add_prefix(row, icon);

        GtkWidget* actions_box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 6);
        gtk_widget_set_valign(actions_box, GTK_ALIGN_CENTER);

        bool installed = std::filesystem::exists(paths::core_path(item.type));
        GtkWidget* btn = gtk_button_new_with_label(installed ? "Обновить" : "Скачать");
        gtk_widget_add_css_class(btn, "suggested-action");
        gtk_widget_add_css_class(btn, "kernel-btn");
        gtk_box_append(GTK_BOX(actions_box), btn);

        GtkWidget* del_btn = gtk_button_new_from_icon_name("user-trash-symbolic");
        gtk_widget_add_css_class(del_btn, "flat");
        gtk_widget_add_css_class(del_btn, "destructive-action");
        gtk_widget_set_visible(del_btn, installed);
        gtk_box_append(GTK_BOX(actions_box), del_btn);

        adw_action_row_add_suffix(row, actions_box);
        adw_preferences_group_add(group, GTK_WIDGET(row));
    }
    adw_preferences_page_add(page, group);

    adw_toolbar_view_set_content(toolbar, GTK_WIDGET(page));
    adw_dialog_set_child(dialog, GTK_WIDGET(toolbar));
    adw_dialog_present(dialog, parent);
}

} // namespace dma2ray::ui
