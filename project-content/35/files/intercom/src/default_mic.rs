//! Making the virtual mic the system's default microphone, and giving the
//! old default back.
//!
//! Many games and websites only ever use the default mic: with the virtual
//! mic as the default, they hear Intercom without being set up.
//!
//! - Linux: `pactl set-default-source`.
//! - Windows: there is no public way. Like every tool that does it
//!   (EarTrumpet, SoundSwitch, nircmd), Intercom uses the system's
//!   undocumented `IPolicyConfig` interface, unchanged since Windows 7.
//!
//! Devices are named by their system id here (cpal's device id): a
//! PulseAudio source name on Linux, an endpoint id on Windows.

use cpal::traits::{DeviceTrait, HostTrait};

/// The id of the system's default mic now.
pub fn current(host: &cpal::Host) -> Option<String> {
    let device = host.default_input_device()?;
    device.id().ok().map(|id| id.id().to_string())
}

/// The id of the virtual mic, if it exists.
pub fn virtual_mic(host: &cpal::Host) -> Option<String> {
    host.input_devices()
        .ok()?
        .filter_map(|d| d.id().ok().map(|id| (d, id.id().to_string())))
        .find(|(d, id)| {
            #[cfg(target_os = "linux")]
            let ours = {
                let _ = d;
                id == crate::virtual_mic::SOURCE_NAME
            };
            #[cfg(not(target_os = "linux"))]
            let ours = {
                let _ = id;
                voice_changer::devices::device_name(d).contains("CABLE Output")
            };
            ours
        })
        .map(|(_, id)| id)
}

/// Makes the mic with this id the default one.
pub fn set(id: &str) -> Result<(), String> {
    #[cfg(target_os = "linux")]
    {
        crate::virtual_mic::pactl(&["set-default-source", id]).map(|_| ())
    }
    #[cfg(windows)]
    {
        windows::set(id)
    }
    #[cfg(not(any(target_os = "linux", windows)))]
    {
        let _ = id;
        Err("not supported on this system".into())
    }
}

// The method names are the interface's own.
#[cfg(windows)]
#[allow(non_snake_case)]
mod windows {
    use std::ffi::c_void;
    use windows::Win32::Media::Audio::{ERole, eCommunications, eConsole, eMultimedia};
    use windows::Win32::System::Com::{
        CLSCTX_ALL, COINIT_APARTMENTTHREADED, CoCreateInstance, CoInitializeEx,
    };
    use windows::core::{GUID, HRESULT, HSTRING, IUnknown, IUnknown_Vtbl, PCWSTR, interface};

    const POLICY_CONFIG_CLIENT: GUID = GUID::from_u128(0x870af99c_171d_4f9e_af0d_e63df40c2bc9);

    /// Only the order of the methods matters: Intercom calls one of them.
    #[interface("f8679f50-850a-41cf-9c72-430f290290c8")]
    unsafe trait IPolicyConfig: IUnknown {
        fn GetMixFormat(&self, id: PCWSTR, format: *mut *mut c_void) -> HRESULT;
        fn GetDeviceFormat(&self, id: PCWSTR, default: i32, format: *mut *mut c_void) -> HRESULT;
        fn ResetDeviceFormat(&self, id: PCWSTR) -> HRESULT;
        fn SetDeviceFormat(&self, id: PCWSTR, format: *mut c_void, mix: *mut c_void) -> HRESULT;
        fn GetProcessingPeriod(
            &self,
            id: PCWSTR,
            default: i32,
            period: *mut i64,
            min: *mut i64,
        ) -> HRESULT;
        fn SetProcessingPeriod(&self, id: PCWSTR, period: *mut i64) -> HRESULT;
        fn GetShareMode(&self, id: PCWSTR, mode: *mut c_void) -> HRESULT;
        fn SetShareMode(&self, id: PCWSTR, mode: *mut c_void) -> HRESULT;
        fn GetPropertyValue(&self, id: PCWSTR, key: *const c_void, value: *mut c_void) -> HRESULT;
        fn SetPropertyValue(&self, id: PCWSTR, key: *const c_void, value: *mut c_void) -> HRESULT;
        fn SetDefaultEndpoint(&self, id: PCWSTR, role: ERole) -> HRESULT;
        fn SetEndpointVisibility(&self, id: PCWSTR, visible: i32) -> HRESULT;
    }

    /// Default for every use: games, media, and calls (Discord asks for that one).
    pub fn set(id: &str) -> Result<(), String> {
        let id = HSTRING::from(id);
        unsafe {
            // The window already started COM on this thread: this only makes sure.
            let _ = CoInitializeEx(None, COINIT_APARTMENTTHREADED);
            let policy: IPolicyConfig =
                CoCreateInstance(&POLICY_CONFIG_CLIENT, None, CLSCTX_ALL)
                    .map_err(|e| format!("the system refused: {}", e.message()))?;
            for role in [eConsole, eMultimedia, eCommunications] {
                policy
                    .SetDefaultEndpoint(PCWSTR(id.as_ptr()), role)
                    .ok()
                    .map_err(|e| format!("the system refused: {}", e.message()))?;
            }
        }
        Ok(())
    }
}
