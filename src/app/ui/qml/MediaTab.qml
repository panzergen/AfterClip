import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import QtMultimedia
import "components"

ColumnLayout {
    id: root

    spacing: 6

    function timeText(seconds) {
        seconds = Math.max(0, Math.floor(seconds))
        const h = Math.floor(seconds / 3600)
        const m = Math.floor((seconds % 3600) / 60)
        const s = seconds % 60
        const pad = (value) => String(value).padStart(2, "0")
        return pad(h) + ":" + pad(m) + ":" + pad(s)
    }

    function playFrom(seconds) {
        player.setPosition(Math.max(0, Math.floor(seconds * 1000)))
        player.play()
    }

    function pausePlayback() {
        player.pause()
    }

    // Video area: 16:9 box anchored to the top, follows the source aspect.
    Item {
        id: videoArea
        Layout.fillWidth: true
        Layout.fillHeight: true

        // The QML MediaPlayer owns playback and all transport state. Its
        // change signals are never routed into Python: the Qt multimedia
        // backend emits them in a context where a JS->Python call corrupts
        // memory (reproducible access violation). Python only receives values
        // at explicit user actions.
        MediaPlayer {
            id: player
            objectName: "mediaPlayer"
            audioOutput: audioOutput
            videoOutput: videoOutput
            playbackRate: media.speedValue
            source: media.sourceUrl
        }

        AudioOutput {
            id: audioOutput
        }

        Rectangle {
            id: videoBox
            width: Math.min(parent.width, parent.height * media.aspect)
            height: width / media.aspect
            color: Theme.videoBox
            radius: 4
            border.color: "#333333"

            VideoOutput {
                id: videoOutput
                anchors.fill: parent
                fillMode: VideoOutput.PreserveAspectFit
            }
        }

        Text {
            anchors.centerIn: videoBox
            text: qsTr("Select or drop a media file")
            visible: !session.currentInput
            color: "#666666"
            font.pixelSize: Theme.fontSizeSmall
        }

        Connections {
            target: session
            function onJobRunningChanged() {
                if (session.jobRunning)
                    player.pause()
            }
        }
    }

    // Skip to the nearest bookmark / clip boundary in the given direction
    // (+1 forward, -1 back); fall back to the clip end / start.
    function skip(direction) {
        if (player.source.toString().length === 0)
            return
        const position = player.position / 1000
        const moments = [media.clipStartSec, media.clipEndSec]
        const marks = media.highlightTimes
        for (let i = 0; i < marks.length; i++)
            moments.push(marks[i])
        let target = null
        for (let i = 0; i < moments.length; i++) {
            const moment = moments[i]
            if (direction > 0) {
                if (moment > position + 0.25 && (target === null || moment < target))
                    target = moment
            } else if (moment < position - 0.25 && (target === null || moment > target)) {
                target = moment
            }
        }
        if (target === null)
            target = direction > 0 ? media.clipEndSec : media.clipStartSec
        player.setPosition(Math.max(0, target * 1000))
    }

    // Transport row
    RowLayout {
        Layout.fillWidth: true
        spacing: 6

        IconButton {
            id: playToggle
            glyph: player.playbackState === MediaPlayer.PlayingState ? "\u23F8" : "\u25B6"
            toolTip: qsTr("Play or pause video")
            onClicked: player.playbackState === MediaPlayer.PlayingState
                       ? player.pause()
                       : player.play()
        }

        IconButton {
            glyph: "\u23EE"
            toolTip: qsTr("Skip to the previous bookmark or clip start")
            onClicked: root.skip(-1)
        }

        IconButton {
            glyph: "\u25A0"
            toolTip: qsTr("Stop")
            onClicked: player.pause()
        }

        IconButton {
            glyph: "\u23ED"
            toolTip: qsTr("Skip to the next bookmark or clip end")
            onClicked: root.skip(1)
        }

        IconButton {
            glyph: media.speedLabel
            toolTip: qsTr("Playback speed")
            onClicked: media.cycleSpeed()
        }

        IconButton {
            id: bookmarkButton
            glyph: "\uD83D\uDD16"
            toolTip: qsTr("Mark this timestamp for later frame extraction and vision analysis")
            onClicked: media.toggleBookmarkAt(player.position / 1000)
        }

        Text {
            text: media.bookmarkCountText
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.muted
        }

        Item { Layout.fillWidth: true }

        Text {
            text: root.timeText(player.position / 1000) + " / " + root.timeText(player.duration / 1000)
            font.pixelSize: Theme.fontSizeSmall
            color: Theme.text
        }

        Item { Layout.fillWidth: true }

        IconButton {
            id: clipToggle
            glyph: "\u2702"
            toolTip: qsTr("Set clip video range")
            showCheckState: true
            checked: media.clipMode
            onClicked: media.clipMode = checked
        }
    }

    TimelineBar {
        id: timeline
        Layout.fillWidth: true
        maximumMs: Math.max(media.rangeMs, player.duration)
        positionMs: player.position
        clipMode: media.clipMode
        clipStartSec: media.clipStartSec
        clipEndSec: media.clipEndSec
        marks: media.highlightTimes
        onMoved: (positionMs) => player.setPosition(positionMs)
        onClipRangeChanged: (startSec, endSec) => media.setClipRange(startSec, endSec)
    }

    Text {
        Layout.fillWidth: true
        text: media.clipWarning
        visible: text.length > 0
        color: Theme.danger
        font.pixelSize: Theme.fontSizeSmall
        font.weight: Font.DemiBold
    }

    Row {
        id: clipBody
        visible: media.clipMode
        spacing: 6

        TextField {
            id: clipStartEdit
            width: 105
            height: Theme.controlHeight
            font.pixelSize: Theme.fontSizeSmall
            text: root.timeText(media.clipStartSec)
            inputMask: "99:99:99"
            onEditingFinished: media.clipStartText = text
            background: Rectangle {
                color: Theme.field
                border.color: clipStartEdit.activeFocus ? Theme.primary : Theme.fieldBorder
                radius: 3
            }
        }

        SpinButtons {
            onStepUp: media.nudgeClipStart(1)
            onStepDown: media.nudgeClipStart(-1)
        }

        Text {
            width: 10
            height: Theme.controlHeight
            text: "-"
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
            color: Theme.muted
        }

        TextField {
            id: clipEndEdit
            width: 105
            height: Theme.controlHeight
            font.pixelSize: Theme.fontSizeSmall
            text: root.timeText(media.clipEndSec)
            inputMask: "99:99:99"
            onEditingFinished: media.clipEndText = text
            background: Rectangle {
                color: Theme.field
                border.color: clipEndEdit.activeFocus ? Theme.primary : Theme.fieldBorder
                radius: 3
            }
        }

        SpinButtons {
            onStepUp: media.nudgeClipEnd(1)
            onStepDown: media.nudgeClipEnd(-1)
        }
    }

    // Keep the clip editors in sync with timeline drags and spin buttons.
    Connections {
        target: media
        function onClipChanged() {
            clipStartEdit.text = root.timeText(media.clipStartSec)
            clipEndEdit.text = root.timeText(media.clipEndSec)
        }
    }

    function isBookmarked(timestamp) {
        const marks = media.highlightTimes
        for (let i = 0; i < marks.length; i++) {
            if (Math.abs(marks[i] - timestamp) < 0.5)
                return true
        }
        return false
    }

    // Filmstrip of cached preview frames
    ListView {
        id: filmstrip
        visible: media.frames.length > 0
        Layout.fillWidth: true
        Layout.preferredHeight: 92
        orientation: ListView.Horizontal
        spacing: 4
        clip: true
        model: media.frames
        delegate: Rectangle {
            id: filmFrame
            required property int index
            required property var modelData
            readonly property bool marked: root.isBookmarked(filmFrame.modelData.timestamp)
            width: 112
            height: 63
            color: "#333333"
            border.color: filmFrame.marked
                          ? Theme.bookmark
                          : (filmstrip.currentIndex === filmFrame.index ? Theme.primary : "#999999")
            border.width: filmFrame.marked ? 3 : 1
            radius: 2

            Image {
                anchors.fill: parent
                source: filmFrame.modelData.path
                fillMode: Image.PreserveAspectCrop
                sourceSize: Qt.size(112, 63)
                asynchronous: true
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 1
                text: filmFrame.modelData.label
                font.pixelSize: 9
                color: "#dddddd"
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    filmstrip.currentIndex = filmFrame.index
                    root.playFrom(filmFrame.modelData.timestamp)
                }
            }
        }
    }

    // Metadata bar: name + apply pencil + one-line stats
    RowLayout {
        Layout.fillWidth: true
        spacing: 8

        TextField {
            id: metadataName
            Layout.fillWidth: true
            Layout.preferredWidth: 100
            height: Theme.controlHeight
            placeholderText: qsTr("Output folder name or recording name")
            font.pixelSize: Theme.fontSizeSmall
            selectByMouse: true
            onTextEdited: media.name = text
            background: Rectangle {
                color: Theme.field
                border.color: metadataName.activeFocus ? Theme.primary : Theme.fieldBorder
                radius: 3
            }
            Connections {
                target: media
                function onNameChanged() {
                    if (!metadataName.activeFocus)
                        metadataName.text = media.name
                }
            }
        }

        IconButton {
            glyph: "\u270F"
            toolTip: qsTr("Apply name")
            onClicked: media.applyName = metadataName.text
        }

        Text {
            id: metadataStats
            Layout.fillWidth: true
            Layout.preferredWidth: 200
            text: media.metadataText
            font.pixelSize: Theme.fontSizeCaption
            color: Theme.muted
            elide: Text.ElideRight

            HoverHandler {
                onHoveredChanged: metadataStats.ToolTip.visible = hovered && metadataStats.text.length > 0
            }
            ToolTip.text: metadataStats.text
            ToolTip.delay: 400
        }
    }
}
