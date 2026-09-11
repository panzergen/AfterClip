import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import "components"

ColumnLayout {
    id: root

    spacing: 8

    Text {
        text: qsTr("Record audio to the selected output folder")
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.muted
    }

    CheckBox {
        id: micCheck
        text: qsTr("Microphone")
        checked: record.micSelected
        onToggled: record.micSelected = checked
        font.pixelSize: Theme.fontSizeSmall
    }

    CheckBox {
        id: systemCheck
        text: qsTr("System audio")
        checked: record.systemSelected
        enabled: record.systemSupported
        onToggled: record.systemSelected = checked
        font.pixelSize: Theme.fontSizeSmall
        ToolTip.visible: hovered && !record.systemSupported
        ToolTip.delay: 400
        ToolTip.text: qsTr("Unavailable: this FFmpeg build does not support Windows WASAPI audio capture.")
    }

    ComboBox {
        id: deviceCombo
        Layout.fillWidth: true
        Layout.maximumWidth: 360
        model: record.devices
        font.pixelSize: Theme.fontSizeSmall
        onActivated: (index) => record.device = currentValue
        Component.onCompleted: {
            if (count > 1) {
                currentIndex = 1
                record.device = currentValue
            }
        }
    }

    Row {
        spacing: 8

        Button {
            id: recordButton
            text: qsTr("Record")
            enabled: !record.recording
            font.pixelSize: Theme.fontSizeSmall
            onClicked: record.startRecording()
        }

        Button {
            id: stopButton
            text: qsTr("Stop")
            enabled: record.recording
            font.pixelSize: Theme.fontSizeSmall
            onClicked: record.stopRecording()
        }
    }

    Text {
        text: record.statusText
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.muted
    }
}
