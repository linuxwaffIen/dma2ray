#pragma once

#include "dma2ray/state.hpp"
#include "dma2ray/manager.hpp"
#include <adwaita.h>
#include <map>
#include <optional>
#include <memory>
#include <string>
#include <functional>

namespace dma2ray::ui {

class MainWindow {
public:
    MainWindow(AdwApplication* app, state::Store& store, manager::CoreManager& core_mgr);
    ~MainWindow();
    void present();
    GtkWidget* widget() const { return window_; }

    void show_toast(const std::string& msg);

    // Dialogs
    void show_kernels_dialog();
    void show_about_dialog();
    void show_log_dialog();
    void show_add_profile_dialog();
    void show_add_subscription_dialog();
    void show_rename_profile_dialog(const std::string& id);
    void show_remove_profile_dialog(const std::string& id);
    void show_remove_subscription_dialog(const std::string& id);

    // Actions
    void toggle_connection();
    void select_profile(const std::string& id);
    void connect_profile(const std::string& id);
    void quick_connect();
    void ping_profile(const std::string& id);
    void ping_all_profiles();
    void run_speed_test();
    void update_subscription(const std::string& id);
    void update_all_subscriptions();
    void toggle_sort();

    // UI Updates
    void refresh_all();
    void refresh_ui_status();
    void refresh_profiles_list();
    void refresh_subscriptions_list();
    void update_server_card();

private:
    AdwApplication* app_;
    state::Store& store_;
    manager::CoreManager& core_mgr_;

    GtkWidget* window_ = nullptr;
    GtkWidget* toast_overlay_ = nullptr;
    GtkWidget* header_title_ = nullptr;
    GtkWidget* view_stack_ = nullptr;

    // Home widgets
    GtkWidget* status_label_ = nullptr;
    GtkWidget* detail_label_ = nullptr;
    GtkWidget* big_button_ = nullptr;
    GtkWidget* big_icon_ = nullptr;
    GtkWidget* server_card_ = nullptr;
    GtkWidget* card_flag_ = nullptr;
    GtkWidget* card_name_ = nullptr;
    GtkWidget* card_addr_ = nullptr;
    GtkWidget* card_latency_ = nullptr;
    GtkWidget* home_hint_ = nullptr;
    GtkWidget* quick_entry_ = nullptr;
    GtkWidget* speed_button_ = nullptr;
    GtkWidget* speed_latency_row_ = nullptr;
    GtkWidget* speed_down_row_ = nullptr;

    // Servers widgets
    GtkWidget* profiles_group_ = nullptr;
    GtkWidget* profiles_list_box_ = nullptr;
    GtkWidget* sort_btn_ = nullptr;
    GtkWidget* subs_group_ = nullptr;
    GtkWidget* subs_list_box_ = nullptr;

    // Latency cache
    std::map<std::string, std::optional<int>> latencies_;
    std::map<std::string, GtkWidget*> latency_labels_;
    bool speed_running_ = false;
    guint log_timeout_ = 0;

    void build_ui();
    GtkWidget* build_home_page();
    GtkWidget* build_servers_page();
    GtkWidget* build_settings_page();
    void update_latency_label(GtkWidget* label, const std::optional<int>& ms);
};

void show_dialog_kernels(GtkWidget* parent, state::Store& store, manager::CoreManager* core_mgr, std::function<void(const std::string&)> toast_fn);

} // namespace dma2ray::ui
