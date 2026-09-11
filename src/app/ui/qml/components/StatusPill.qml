import QtQuick

Rectangle {
    id: root

    property string status: "pending"

    function pillColors(status) {
        switch (status) {
        case "running": return { bg: Theme.pillRunningBg, fg: Theme.pillRunningFg }
        case "completed": return { bg: Theme.pillCompletedBg, fg: Theme.pillCompletedFg }
        case "failed": return { bg: Theme.pillFailedBg, fg: Theme.pillFailedFg }
        case "cancelled": return { bg: Theme.pillFailedBg, fg: Theme.pillFailedFg }
        default: return { bg: Theme.pillPendingBg, fg: Theme.pillPendingFg }
        }
    }

    readonly property var colors: pillColors(status)

    implicitWidth: label.implicitWidth + 16
    implicitHeight: 18
    radius: 9
    color: colors.bg

    Text {
        id: label
        anchors.centerIn: parent
        text: root.status
        font.pixelSize: 10
        font.weight: Font.DemiBold
        color: root.colors.fg
    }
}
