pragma Singleton
import QtQuick

QtObject {
    // Surfaces and text (mockup rev 2)
    readonly property color background: "#f0f0f0"
    readonly property color panel: "#fafafa"
    readonly property color field: "#ffffff"
    readonly property color titlebar: "#e4e6ea"
    readonly property color border: "#c9c9c9"
    readonly property color fieldBorder: "#b6b6b6"
    readonly property color text: "#222222"
    readonly property color muted: "#555555"
    readonly property color faint: "#9a9a9a"

    // Accents
    readonly property color primary: "#0a7bd6"
    readonly property color primaryHover: "#3fa2ff"
    readonly property color danger: "#b3261e"
    readonly property color warn: "#8a5a00"
    readonly property color ok: "#1c7a2e"

    // Timeline
    readonly property color rail: "#c4c9d1"
    readonly property color clip: "#2589d8"
    readonly property color knob: "#087dcc"
    readonly property color head: "#20242b"
    readonly property color bookmark: "#f0b429"

    // LED + pills
    readonly property color ledGreen: "#2e9e44"
    readonly property color ledRed: "#c62828"
    readonly property color pillPendingBg: "#e8f0fe"
    readonly property color pillPendingFg: "#1a56b0"
    readonly property color pillRunningBg: "#fff4d6"
    readonly property color pillRunningFg: "#8a5a00"
    readonly property color pillCompletedBg: "#e5f3e6"
    readonly property color pillCompletedFg: "#1c7a2e"
    readonly property color pillFailedBg: "#fde7e7"
    readonly property color pillFailedFg: "#b3261e"

    // Video + log
    readonly property color videoBox: "#17191d"
    readonly property color logBg: "#20242b"
    readonly property color logFg: "#c8f0c8"
    readonly property color popupBg: "#2b2f36"
    readonly property color popupFg: "#e8eaed"

    // Type scale (dense desktop tool, mockup parity)
    readonly property int fontSizeBody: 13
    readonly property int fontSizeSmall: 12
    readonly property int fontSizeCaption: 11

    readonly property int controlHeight: 30
    readonly property int iconButtonSize: 36
}
