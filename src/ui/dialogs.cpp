#include "dma2ray/window.hpp"
#include "dma2ray/paths.hpp"
#include "dma2ray/installer.hpp"

#include <filesystem>
#include <thread>

namespace dma2ray::ui {

struct KernelRowContext {
    std::string type;
    std::string title;
    std::string subtitle;
    AdwActionRow* row = nullptr;
    GtkWidget* btn = nullptr;
    GtkWidget* del_btn = nullptr;
    state::Store* store = nullptr;
    manager::CoreManager* core_mgr = nullptr;
    std::function<void(const std::string&)> toast_fn;
};

void show_dialog_kernels(GtkWidget* parent, state::Store& store, manager::CoreManager* core_mgr, std::function<void(const std::string&)> toast_fn) {
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

        auto* ctx = new KernelRowContext{
            item.type,
            item.title,
            item.subtitle,
            row,
            btn,
            del_btn,
            &store,
            core_mgr,
            toast_fn
        };
        g_object_set_data_full(G_OBJECT(row), "kernel_ctx", ctx, +[](gpointer d) {
            delete static_cast<KernelRowContext*>(d);
        });

        // Download / Update button click handler
        g_signal_connect(btn, "clicked", G_CALLBACK(+[](GtkButton*, gpointer user_data) {
            auto* c = static_cast<KernelRowContext*>(user_data);
            if (c->core_mgr && c->core_mgr->get_status().state == manager::State::Running) {
                if (c->toast_fn) c->toast_fn("Сначала отключитесь, затем обновите ядро");
                return;
            }

            gtk_widget_set_sensitive(c->btn, FALSE);
            gtk_button_set_label(GTK_BUTTON(c->btn), "Загрузка…");
            if (c->del_btn) gtk_widget_set_sensitive(c->del_btn, FALSE);

            std::string k_type = c->type;
            std::string k_title = c->title;
            std::string k_sub = c->subtitle;
            AdwActionRow* r = c->row;
            GtkWidget* b = c->btn;
            GtkWidget* db = c->del_btn;
            auto toast = c->toast_fn;

            std::thread([k_type, k_title, k_sub, r, b, db, toast]() {
                auto on_prog = [r](double fraction, const std::string&) {
                    int pct = static_cast<int>(fraction * 100.0);
                    if (pct < 0) pct = 0;
                    if (pct > 100) pct = 100;
                    std::string prog_text = "Загрузка " + std::to_string(pct) + "%";

                    struct ProgData {
                        AdwActionRow* row;
                        std::string msg;
                    };
                    auto* pd = new ProgData{r, prog_text};
                    g_idle_add(+[](gpointer p) -> gboolean {
                        auto* data = static_cast<ProgData*>(p);
                        adw_action_row_set_subtitle(data->row, data->msg.c_str());
                        delete data;
                        return G_SOURCE_REMOVE;
                    }, pd);
                };

                bool ok = installer::install_kernel(k_type, paths::current_arch(), on_prog);

                struct DoneData {
                    AdwActionRow* row;
                    GtkWidget* btn;
                    GtkWidget* del_btn;
                    std::string title;
                    std::string sub;
                    bool success;
                    std::string type;
                    std::function<void(const std::string&)> toast;
                };
                auto* dd = new DoneData{r, b, db, k_title, k_sub, ok, k_type, toast};

                g_idle_add(+[](gpointer p) -> gboolean {
                    auto* data = static_cast<DoneData*>(p);
                    gtk_widget_set_sensitive(data->btn, TRUE);
                    if (data->del_btn) gtk_widget_set_sensitive(data->del_btn, TRUE);
                    adw_action_row_set_subtitle(data->row, data->sub.c_str());

                    if (data->success) {
                        gtk_button_set_label(GTK_BUTTON(data->btn), "Обновить");
                        if (data->del_btn) gtk_widget_set_visible(data->del_btn, TRUE);
                        if (data->toast) data->toast(data->title + " установлен");
                    } else {
                        bool exists = std::filesystem::exists(paths::core_path(data->type));
                        gtk_button_set_label(GTK_BUTTON(data->btn), exists ? "Обновить" : "Скачать");
                        if (data->toast) data->toast("Не удалось установить " + data->title);
                    }
                    delete data;
                    return G_SOURCE_REMOVE;
                }, dd);
            }).detach();
        }), ctx);

        // Delete button click handler
        g_signal_connect(del_btn, "clicked", G_CALLBACK(+[](GtkButton*, gpointer user_data) {
            auto* c = static_cast<KernelRowContext*>(user_data);
            if (c->core_mgr && c->core_mgr->get_status().state == manager::State::Running) {
                if (c->toast_fn) c->toast_fn("Нельзя удалить ядро во время активного подключения");
                return;
            }

            std::string heading = "Удалить " + c->title + "?";
            std::string body = "Файлы ядра " + c->title + " для архитектуры " + paths::current_arch() + " будут удалены с диска.";
            AdwAlertDialog* alert = ADW_ALERT_DIALOG(adw_alert_dialog_new(heading.c_str(), body.c_str()));
            adw_alert_dialog_add_response(alert, "cancel", "Отмена");
            adw_alert_dialog_add_response(alert, "delete", "Удалить");
            adw_alert_dialog_set_response_appearance(alert, "delete", ADW_RESPONSE_DESTRUCTIVE);
            adw_alert_dialog_set_default_response(alert, "cancel");
            adw_alert_dialog_set_close_response(alert, "cancel");

            struct DelData {
                KernelRowContext* ctx;
            };
            auto* dd = new DelData{c};

            GtkWidget* root_win = GTK_WIDGET(gtk_widget_get_root(GTK_WIDGET(c->btn)));
            adw_alert_dialog_choose(alert, root_win, nullptr, +[](GObject* src, GAsyncResult* res, gpointer user_data) {
                auto* dd = static_cast<DelData*>(user_data);
                auto* alert_obj = ADW_ALERT_DIALOG(src);
                const char* resp = adw_alert_dialog_choose_finish(alert_obj, res);
                if (resp && std::string(resp) == "delete") {
                    std::error_code ec;
                    std::filesystem::remove_all(paths::core_dir(dd->ctx->type), ec);
                    std::filesystem::remove(paths::core_path(dd->ctx->type), ec);

                    gtk_button_set_label(GTK_BUTTON(dd->ctx->btn), "Скачать");
                    gtk_widget_set_visible(dd->ctx->del_btn, FALSE);
                    adw_action_row_set_subtitle(dd->ctx->row, dd->ctx->subtitle.c_str());
                    if (dd->ctx->toast_fn) dd->ctx->toast_fn(dd->ctx->title + " удалено");
                }
                delete dd;
            }, dd);
        }), ctx);

        adw_action_row_add_suffix(row, actions_box);
        adw_preferences_group_add(group, GTK_WIDGET(row));
    }
    adw_preferences_page_add(page, group);

    adw_toolbar_view_set_content(toolbar, GTK_WIDGET(page));
    adw_dialog_set_child(dialog, GTK_WIDGET(toolbar));
    adw_dialog_present(dialog, parent);
}

} // namespace dma2ray::ui