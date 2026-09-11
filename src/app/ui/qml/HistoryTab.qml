import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import "components"

ColumnLayout {
    id: root

    spacing: 8

    Text {
        text: qsTr("Processed jobs (newest first) — select one to view its report.")
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.muted
    }

    ListView {
        id: jobsList
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        model: history.model
        currentIndex: -1
        highlightFollowsCurrentItem: true

        delegate: ItemDelegate {
            id: rowDelegate
            required property int index
            required property string name
            required property string status
            width: jobsList.width
            highlighted: ListView.isCurrentItem
            font.pixelSize: Theme.fontSizeSmall
            text: rowDelegate.name + " — " + rowDelegate.status
            onClicked: {
                jobsList.currentIndex = rowDelegate.index
                history.selectRow(rowDelegate.index)
            }
        }

        Text {
            anchors.centerIn: parent
            visible: jobsList.count === 0
            text: qsTr("No processed jobs yet")
            color: Theme.faint
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    Flow {
        Layout.fillWidth: true
        spacing: 8

        Button {
            text: qsTr("Refresh")
            font.pixelSize: Theme.fontSizeSmall
            onClicked: history.refresh()
        }

        Button {
            text: qsTr("Open job folder")
            font.pixelSize: Theme.fontSizeSmall
            onClicked: history.openSelectedFolder()
        }
    }

    ScrollView {
        Layout.fillWidth: true
        Layout.fillHeight: true
        TextArea {
            id: detailsView
            readOnly: true
            text: history.detailsText
            wrapMode: TextArea.Wrap
            font.pixelSize: Theme.fontSizeCaption
            color: Theme.text
        }
    }

    Text {
        text: qsTr("Application log (last 400 lines)")
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.muted
    }

    ScrollView {
        Layout.fillWidth: true
        Layout.preferredHeight: 140
        TextArea {
            readOnly: true
            text: history.logText
            wrapMode: TextArea.NoWrap
            font.pixelSize: Theme.fontSizeCaption
            font.family: "Consolas"
            color: Theme.logFg
            background: Rectangle {
                color: Theme.logBg
                radius: 3
            }
        }
    }
}
