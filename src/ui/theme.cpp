#include "dma2ray/theme.hpp"

namespace dma2ray::ui {

static const char* APP_CSS = R"(
@define-color accent_bg_color #2f6bd8;
@define-color accent_fg_color #ffffff;
@define-color accent_color #3a7be8;

switch:checked {
    background-color: #2f6bd8;
}
.latency-good { color: #26a269; }
.latency-ok { color: #e5a50a; }
.latency-bad { color: #c01c28; }
.latency-unknown { color: alpha(currentColor, 0.5); }
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
.connect-busy { background-color: #e5a50a; }
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
.dialog button.kernel-btn,
button.kernel-btn,
.kernel-btn {
    min-width: 96px;
    min-height: 34px;
    border-radius: 999px;
    font-weight: 600;
}
.kernel-icon {
    background-color: alpha(currentColor, 0.08);
    border-radius: 12px;
    padding: 10px;
}
)";

void install_custom_css() {
    GtkCssProvider* provider = gtk_css_provider_new();
    gtk_css_provider_load_from_data(provider, APP_CSS, -1);
    gtk_style_context_add_provider_for_display(
        gdk_display_get_default(),
        GTK_STYLE_PROVIDER(provider),
        GTK_STYLE_PROVIDER_PRIORITY_APPLICATION
    );
    g_object_unref(provider);
}

void apply_theme(const std::string& scheme) {
    AdwStyleManager* sm = adw_style_manager_get_default();
    if (scheme == "dark") {
        adw_style_manager_set_color_scheme(sm, ADW_COLOR_SCHEME_FORCE_DARK);
    } else if (scheme == "light") {
        adw_style_manager_set_color_scheme(sm, ADW_COLOR_SCHEME_FORCE_LIGHT);
    } else {
        adw_style_manager_set_color_scheme(sm, ADW_COLOR_SCHEME_DEFAULT);
    }
}

} // namespace dma2ray::ui
