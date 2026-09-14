import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import "components"

ColumnLayout {
    id: root

    signal settingsRequested()

    Layout.fillWidth: true
    spacing: 6

    ProgressBar {
        Layout.fillWidth: true
        from: 0
        to: 100
        value: session.progressValue
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 10

        Text {
            Layout.fillWidth: true
            text: session.statusText
            font.pixelSize: Theme.fontSizeSmall
            elide: Text.ElideRight
        }

        Text {
            text: qsTr("\uD83D\uDCC2 Open output folder")
            visible: session.hasOutputFolder
            font.pixelSize: Theme.fontSizeSmall
            font.underline: true
            color: Theme.primary
            Accessible.role: Accessible.Link
            Accessible.name: text

            ToolTip.visible: outputLinkMouse.containsMouse
            ToolTip.delay: 300
            ToolTip.text: session.outputFolder

            MouseArea {
                id: outputLinkMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: session.openOutputFolder()
            }
        }

        StatusLed {
            ok: env.ok
            checksText: env.checksText
        }

        IconButton {
            glyph: "\u2699"
            toolTip: qsTr("Settings")
            onClicked: root.settingsRequested()
        }
    }

    RowLayout {
        Layout.fillWidth: true
        spacing: 8

        Button {
            id: startButton
            Layout.fillWidth: true
            text: qsTr("Start Processing")
            enabled: session.startEnabled
            font.pixelSize: Theme.fontSizeSmall
            font.weight: Font.DemiBold
            onClicked: session.startJob()

            background: Rectangle {
                color: !startButton.enabled ? "#a9c9e8" : (startButton.hovered ? Theme.primaryHover : Theme.primary)
                radius: 3
            }
            contentItem: Text {
                text: startButton.text
                color: "#ffffff"
                font: startButton.font
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }

        Button {
            text: qsTr("Cancel")
            enabled: session.cancelEnabled
            font.pixelSize: Theme.fontSizeSmall
            onClicked: session.cancelJob()
        }
    }
}
