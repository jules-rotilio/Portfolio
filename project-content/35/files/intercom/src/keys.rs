//! The keys Intercom can react to, with one name each.
//!
//! Linux reports keys by their position on the keyboard (evdev codes), Windows
//! by "virtual key" numbers. Both are turned into this one list, so the
//! settings file says `"Num1"` or `"F9"` whatever the system.

use serde::{Deserialize, Serialize};

/// Declares the `Key` enum together with each key's file name, its label in
/// the window, its Linux evdev code and its Windows virtual-key code, so the
/// four never drift apart.
macro_rules! keys {
    ($($variant:ident $name:literal $label:literal $linux:literal $windows:literal;)*) => {
        #[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
        #[serde(try_from = "String", into = "String")]
        pub enum Key { $($variant,)* }

        impl Key {
            pub const ALL: &[Key] = &[$(Key::$variant,)*];

            /// The name used in the settings file.
            pub fn name(self) -> &'static str {
                match self { $(Key::$variant => $name,)* }
            }

            /// The short label shown on screen.
            pub fn label(self) -> &'static str {
                match self { $(Key::$variant => $label,)* }
            }

            pub fn from_name(name: &str) -> Option<Key> {
                match name { $($name => Some(Key::$variant),)* _ => None }
            }

            /// The key for a Linux evdev key code.
            pub fn from_linux(code: u16) -> Option<Key> {
                match code { $($linux => Some(Key::$variant),)* _ => None }
            }

            #[cfg(test)]
            fn linux_code(self) -> u16 {
                match self { $(Key::$variant => $linux,)* }
            }

            /// The Windows virtual-key code, before the numpad rules in `from_windows`.
            fn windows_vk(self) -> u32 {
                match self { $(Key::$variant => $windows,)* }
            }
        }
    };
}

keys! {
    // The numpad. Windows codes are those with NumLock on; see `from_windows`.
    Num0 "Num0" "0" 82 0x60;
    Num1 "Num1" "1" 79 0x61;
    Num2 "Num2" "2" 80 0x62;
    Num3 "Num3" "3" 81 0x63;
    Num4 "Num4" "4" 75 0x64;
    Num5 "Num5" "5" 76 0x65;
    Num6 "Num6" "6" 77 0x66;
    Num7 "Num7" "7" 71 0x67;
    Num8 "Num8" "8" 72 0x68;
    Num9 "Num9" "9" 73 0x69;
    NumStar "NumStar" "*" 55 0x6A;
    NumPlus "NumPlus" "+" 78 0x6B;
    NumMinus "NumMinus" "-" 74 0x6D;
    NumDot "NumDot" "." 83 0x6E;
    NumSlash "NumSlash" "/" 98 0x6F;
    NumEnter "NumEnter" "Enter" 96 0x0D;
    NumLock "NumLock" "NumLk" 69 0x90;
    // Navigation.
    Up "Up" "↑" 103 0x26;
    Down "Down" "↓" 108 0x28;
    Left "Left" "←" 105 0x25;
    Right "Right" "→" 106 0x27;
    PageUp "PageUp" "PgUp" 104 0x21;
    PageDown "PageDown" "PgDn" 109 0x22;
    Home "Home" "Home" 102 0x24;
    End "End" "End" 107 0x23;
    Insert "Insert" "Ins" 110 0x2D;
    Delete "Delete" "Del" 111 0x2E;
    // Others.
    Escape "Escape" "Esc" 1 0x1B;
    Space "Space" "Space" 57 0x20;
    Tab "Tab" "Tab" 15 0x09;
    Enter "Enter" "↵" 28 0x0D;
    ScrollLock "ScrollLock" "ScrLk" 70 0x91;
    Pause "Pause" "Pause" 119 0x13;
    F1 "F1" "F1" 59 0x70;
    F2 "F2" "F2" 60 0x71;
    F3 "F3" "F3" 61 0x72;
    F4 "F4" "F4" 62 0x73;
    F5 "F5" "F5" 63 0x74;
    F6 "F6" "F6" 64 0x75;
    F7 "F7" "F7" 65 0x76;
    F8 "F8" "F8" 66 0x77;
    F9 "F9" "F9" 67 0x78;
    F10 "F10" "F10" 68 0x79;
    F11 "F11" "F11" 87 0x7A;
    F12 "F12" "F12" 88 0x7B;
    F13 "F13" "F13" 183 0x7C;
    F14 "F14" "F14" 184 0x7D;
    F15 "F15" "F15" 185 0x7E;
    F16 "F16" "F16" 186 0x7F;
    F17 "F17" "F17" 187 0x80;
    F18 "F18" "F18" 188 0x81;
    F19 "F19" "F19" 189 0x82;
    F20 "F20" "F20" 190 0x83;
    F21 "F21" "F21" 191 0x84;
    F22 "F22" "F22" 192 0x85;
    F23 "F23" "F23" 193 0x86;
    F24 "F24" "F24" 194 0x87;
    // Letters and the digit row (Linux codes are key positions on a US layout).
    A "A" "A" 30 0x41; B "B" "B" 48 0x42; C "C" "C" 46 0x43; D "D" "D" 32 0x44;
    E "E" "E" 18 0x45; F "F" "F" 33 0x46; G "G" "G" 34 0x47; H "H" "H" 35 0x48;
    I "I" "I" 23 0x49; J "J" "J" 36 0x4A; K "K" "K" 37 0x4B; L "L" "L" 38 0x4C;
    M "M" "M" 50 0x4D; N "N" "N" 49 0x4E; O "O" "O" 24 0x4F; P "P" "P" 25 0x50;
    Q "Q" "Q" 16 0x51; R "R" "R" 19 0x52; S "S" "S" 31 0x53; T "T" "T" 20 0x54;
    U "U" "U" 22 0x55; V "V" "V" 47 0x56; W "W" "W" 17 0x57; X "X" "X" 45 0x58;
    Y "Y" "Y" 21 0x59; Z "Z" "Z" 44 0x5A;
    Digit0 "0" "0" 11 0x30; Digit1 "1" "1" 2 0x31; Digit2 "2" "2" 3 0x32;
    Digit3 "3" "3" 4 0x33; Digit4 "4" "4" 5 0x34; Digit5 "5" "5" 6 0x35;
    Digit6 "6" "6" 7 0x36; Digit7 "7" "7" 8 0x37; Digit8 "8" "8" 9 0x38;
    Digit9 "9" "9" 10 0x39;
}

impl Key {
    /// The key for a Windows virtual-key code. `extended` is the hook's
    /// "extended key" flag. It tells the numpad from the keys it copies: with
    /// NumLock off, Num 1 sends the same code as End, but without the flag;
    /// Enter and Num Enter differ only by it.
    pub fn from_windows(vk: u32, extended: bool) -> Option<Key> {
        const CLEAR: u32 = 0x0C; // Num 5 with NumLock off
        let numpad_copy = match vk {
            0x24 => Some(Key::Num7),
            0x26 => Some(Key::Num8),
            0x21 => Some(Key::Num9),
            0x25 => Some(Key::Num4),
            CLEAR => Some(Key::Num5),
            0x27 => Some(Key::Num6),
            0x23 => Some(Key::Num1),
            0x28 => Some(Key::Num2),
            0x22 => Some(Key::Num3),
            0x2D => Some(Key::Num0),
            0x2E => Some(Key::NumDot),
            _ => None,
        };
        if !extended && numpad_copy.is_some() {
            return numpad_copy;
        }
        if vk == 0x0D {
            return Some(if extended { Key::NumEnter } else { Key::Enter });
        }
        Key::ALL
            .iter()
            .copied()
            .find(|k| k.windows_vk() == vk && *k != Key::NumEnter)
    }

    /// The keys that play sounds, in the order the Sounds tab lists them.
    pub const SOUND_KEYS: [Key; 15] = [
        Key::Num0,
        Key::Num1,
        Key::Num2,
        Key::Num3,
        Key::Num4,
        Key::Num5,
        Key::Num6,
        Key::Num7,
        Key::Num8,
        Key::Num9,
        Key::NumSlash,
        Key::NumStar,
        Key::NumMinus,
        Key::NumPlus,
        Key::NumEnter,
    ];
}

impl From<Key> for String {
    fn from(key: Key) -> String {
        key.name().to_string()
    }
}

impl TryFrom<String> for Key {
    type Error = String;
    fn try_from(name: String) -> Result<Key, String> {
        Key::from_name(&name).ok_or_else(|| format!("unknown key name `{name}`"))
    }
}

impl std::fmt::Display for Key {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.label())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_round_trip_and_are_unique() {
        for &key in Key::ALL {
            assert_eq!(Key::from_name(key.name()), Some(key));
        }
        let mut names: Vec<_> = Key::ALL.iter().map(|k| k.name()).collect();
        names.sort();
        names.dedup();
        assert_eq!(names.len(), Key::ALL.len());
    }

    #[test]
    fn linux_codes_are_unique() {
        for &key in Key::ALL {
            assert_eq!(Key::from_linux(key.linux_code()), Some(key), "{key:?}");
        }
    }

    // With NumLock off, Windows sends navigation codes for the numpad; only
    // the "extended" flag tells them apart from the real arrows.
    #[test]
    fn windows_numpad_and_arrows_are_told_apart() {
        assert_eq!(Key::from_windows(0x23, false), Some(Key::Num1));
        assert_eq!(Key::from_windows(0x23, true), Some(Key::End));
        assert_eq!(Key::from_windows(0x26, true), Some(Key::Up));
        assert_eq!(Key::from_windows(0x26, false), Some(Key::Num8));
        assert_eq!(Key::from_windows(0x61, false), Some(Key::Num1));
        assert_eq!(Key::from_windows(0x0D, true), Some(Key::NumEnter));
        assert_eq!(Key::from_windows(0x0D, false), Some(Key::Enter));
        assert_eq!(Key::from_windows(0x78, false), Some(Key::F9));
        assert_eq!(Key::from_windows(0x6F, true), Some(Key::NumSlash));
    }

    #[test]
    fn serializes_as_its_name() {
        #[derive(Serialize, Deserialize, PartialEq, Debug)]
        struct S {
            k: Key,
        }
        let text = toml::to_string(&S { k: Key::PageDown }).unwrap();
        assert_eq!(text.trim(), r#"k = "PageDown""#);
        assert_eq!(toml::from_str::<S>(&text).unwrap(), S { k: Key::PageDown });
    }
}
