//! Windows: puts the icon inside Intercom.exe, for Explorer and the taskbar.
//! (The window's own icon is set at run time, in main.rs, on every system.)

fn main() {
    println!("cargo:rerun-if-changed=assets/icon.ico");
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        let mut resource = winresource::WindowsResource::new();
        resource.set_icon("assets/icon.ico");
        // Building for Windows from Linux needs MinGW's windres; without
        // it the program still builds, just without the file icon.
        if let Err(e) = resource.compile() {
            println!("cargo:warning=no icon in the .exe: {e}");
        }
    }
}
