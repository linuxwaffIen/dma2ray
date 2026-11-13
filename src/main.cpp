#include "dma2ray/paths.hpp"
#include "dma2ray/state.hpp"
#include "dma2ray/manager.hpp"
#include "dma2ray/theme.hpp"
#include "dma2ray/window.hpp"

#include <adwaita.h>
#include <gdk/gdk.h>
#include <memory>
#include <cstdlib>

static void on_activate(GtkApplication* app, gpointer user_data) {
    auto* store = static_cast<dma2ray::state::Store*>(user_data);
    static std::unique_ptr<dma2ray::manager::CoreManager> core_mgr;
    static std::unique_ptr<dma2ray::ui::MainWindow> main_win;

    if (!core_mgr) {
        core_mgr = std::make_unique<dma2ray::manager::CoreManager>(*store, [](const dma2ray::manager::Status& s) {
            g_idle_add(+[](gpointer p) -> gboolean {
                if (main_win) main_win->refresh_ui_status();
                return G_SOURCE_REMOVE;
            }, nullptr);
        });
    }

    if (!main_win) {
        dma2ray::ui::install_custom_css();
        std::string scheme = store->get_setting("color_scheme", "system").get<std::string>();
        dma2ray::ui::apply_theme(scheme);

        main_win = std::make_unique<dma2ray::ui::MainWindow>(ADW_APPLICATION(app), *store, *core_mgr);
    }
    main_win->present();
}

int main(int argc, char** argv) {
    // Prioritize native Wayland backend if available, fallback to X11
    if (!std::getenv("GDK_BACKEND")) {
        gdk_set_allowed_backends("wayland,x11,*");
    }

    dma2ray::paths::ensure_dirs();
    dma2ray::state::Store store;

    AdwApplication* app = adw_application_new(
        dma2ray::paths::APP_ID.c_str(),
        G_APPLICATION_DEFAULT_FLAGS
    );

    g_signal_connect(app, "activate", G_CALLBACK(on_activate), &store);
    int status = g_application_run(G_APPLICATION(app), argc, argv);
    g_object_unref(app);
    return status;
}
