import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import "components"

ColumnLayout {
    id: root

    signal browseOutputRequested()
    signal browseSupportRequested()

    Layout.fillWidth: true
    spacing: 8

    JobSettingsGroup {
        Layout.fillWidth: true
        onBrowseOutputRequested: root.browseOutputRequested()
        onBrowseSupportRequested: root.browseSupportRequested()
    }

    SegmentedToggle {
        Layout.fillWidth: true
        cloudSelected: jobForm.cloudSelected
        onCloudToggled: jobForm.cloudSelected = true
        onLocalToggled: jobForm.cloudSelected = false
    }

    Text {
        Layout.fillWidth: true
        text: jobForm.aiStatus
        visible: text.length > 0
        font.pixelSize: Theme.fontSizeCaption
        color: jobForm.aiStatusColor
        wrapMode: Text.Wrap
    }

    AdvancedPanel {
        Layout.fillWidth: true
    }
}
