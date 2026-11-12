#pragma once

#include "dma2ray/state.hpp"
#include "dma2ray/manager.hpp"
#include <adwaita.h>

namespace dma2ray::ui {

class MainWindow {
public:
    MainWindow(AdwApplication* app, state::Store& store, manager::CoreManager& core_mgr);
    void present();
    GtkWidget* widget() const { return window_; }

    void show_kernels_dialog();
    void show_about_dialog();
    void show_log_dialog();

    void toggle_connection();
    void refresh_ui_status();
    void refresh_profiles_list();

private:
    AdwApplication* app_;
    state::Store& store_;
    manager::CoreManager& core_mgr_;

    GtkWidget* window_ = nullptr;
    GtkWidget* toast_overlay_ = nullptr;
    GtkWidget* view_stack_ = nullptr;
    GtkWidget* status_label_ = nullptr;
    GtkWidget* detail_label_ = nullptr;
    GtkWidget* big_button_ = nullptr;
    GtkWidget* big_icon_ = nullptr;
    GtkWidget* card_name_ = nullptr;
    GtkWidget* card_addr_ = nullptr;
    GtkWidget* card_latency_ = nullptr;
    GtkWidget* profiles_list_box_ = nullptr;

    void build_ui();
    GtkWidget* build_home_page();
    GtkWidget* build_servers_page();
    GtkWidget* build_settings_page();
};

void show_dialog_kernels(GtkWidget* parent, state::Store& store);

} // namespace dma2ray::ui
