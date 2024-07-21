import sys
import gi
import threading
from PyQt5.QtCore import QEvent, Qt, pyqtSlot, QStandardPaths, QPoint, QTimer
from PyQt5.QtGui import QIcon, QKeySequence, QCursor
from PyQt5.QtWidgets import QMainWindow, QFileDialog, QSizePolicy, QToolBar, QAction, QSlider, QStyle, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QApplication, QDialog
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent, QAudioOutput
from PyQt5.QtMultimediaWidgets import QVideoWidget

# Initialize GStreamer
gi.require_version('Gst', '1.0')
from gi.repository import Gst

AVI = "video/x-msvideo"  # AVI
MP4 = "video/mp4"
TS = "video/mp2t"
FLV = "video/x-flv"
_3GP = "video/3gpp"

def get_supported_mime_types():
	result = [AVI, MP4, TS, FLV, _3GP]
	supported_mime_types = QMediaPlayer.supportedMimeTypes()
	for mime_type in supported_mime_types:
		result.append(mime_type)
	return result

class SeekSlider(QSlider):
	def __init__(self, total_duration, orientation=Qt.Horizontal):
		super().__init__(orientation)
		# Obtain the total duration from the QMediaPlayer
		self.total_duration = total_duration  # Store the total duration

	def reset_position(self):
		self.setValue(0)
		
	def mousePressEvent(self, event):
		if event.button() == Qt.LeftButton:
			value = QStyle.sliderValueFromPosition(
				self.minimum(),
				self.maximum(),
				event.x(),
				self.width()
			)
			self.setValue(value)
			event.accept()
		else:
			super().mousePressEvent(event)
			
	def mouseMoveEvent(self, event):
		if event.buttons() & Qt.LeftButton:
			value = QStyle.sliderValueFromPosition(
				self.minimum(),
				self.maximum(),
				event.x(),
				self.width()
			)
			self.setValue(value)
			event.accept()

		super().mouseMoveEvent(event)
			
class MainWindow(QMainWindow):
	def __init__(self):
		super().__init__()
  
		# Set the window icon
		icon_path = 'sprite.png'  # Replace 'path_to_your_icon' with the actual path
		self.setWindowIcon(QIcon(icon_path))
  
		self._media_player = QMediaPlayer()
		self._mime_types = []  # Initialize the _mime_types attribute as an empty list
		self._delay_timer = QTimer(self)
		self._delay_timer.timeout.connect(self.start_media_playback)
		self._slider = SeekSlider(Qt.Horizontal)  # Create a QSlider instance
		self._playback_time_label = QLabel()  # Create a QLabel instance
		self._total_duration_label = QLabel()  # Create a QLabel instance
		self._video_widget = QVideoWidget()
		
		self._player = QMediaPlayer()
		total_duration = self._player.duration()
		
		Gst.init(None)
		
		# Get the GStreamer bus
		self._bus = Gst.Bus()

		# Add the GStreamer bus watch
		self._bus.add_signal_watch()

		# Connect message handlers for debugging
		self._bus.connect("message::error", self.on_error_message)
		self._bus.connect("message::warning", self.on_warning_message)

		# Create a QVideoWidget instance
		self._video_widget = QVideoWidget()
		# Add the video widget to the layout or set as central widget, etc.
		self.setCentralWidget(self._video_widget)
			 
		self.video_position = 0  # Initialize video_position as an instance variable
		
		# Create a SeekSlider instance with the total duration
		self._slider = SeekSlider(total_duration, Qt.Horizontal)

		self.fullscreen = False  # Initially not in fullscreen mode
		self.tool_bar = QToolBar()  # Create a reference to the toolbar
		
		self.initUI()

	def initUI(self):
		# Create a QMediaPlayer instance
		self._player = QMediaPlayer()  # Update the attribute name to "player"
		self._video_widget = QLabel()
		self._audio_output = QAudioOutput()  # Create a QAudioOutput instance
		self._playlist = []  # FIXME 6.3: Replace by QMediaPlaylist?
		self._playlist_index = -1

		# Make toolbar
		tool_bar = QToolBar()
		self.addToolBar(tool_bar)

		file_menu = self.menuBar().addMenu("&File")
		icon = QIcon.fromTheme("document-open")
		open_action = QAction(icon, "&Open...", self, shortcut=QKeySequence.Open, triggered=self.open)
		file_menu.addAction(open_action)
		tool_bar.addAction(open_action)

		icon = QIcon.fromTheme("application-exit")
		exit_action = QAction(icon, "E&xit", self, shortcut="Ctrl+Q", triggered=self.close)
		file_menu.addAction(exit_action)

		play_menu = self.menuBar().addMenu("&Play")
		style = self.style()

		icon = QIcon.fromTheme("media-playback-start.png", style.standardIcon(QStyle.SP_MediaPlay))
		self._play_action = tool_bar.addAction(icon, "Play")
		self._play_action.triggered.connect(self._player.play)
		play_menu.addAction(self._play_action)

		icon = QIcon.fromTheme("media-skip-backward-symbolic.svg", style.standardIcon(QStyle.SP_MediaSkipBackward))
		self._previous_action = tool_bar.addAction(icon, "Previous")
		self._previous_action.triggered.connect(self.previous_clicked)
		play_menu.addAction(self._previous_action)

		icon = QIcon.fromTheme("media-playback-pause.png", style.standardIcon(QStyle.SP_MediaPause))
		self._pause_action = tool_bar.addAction(icon, "Pause")
		self._pause_action.triggered.connect(self._player.pause)
		play_menu.addAction(self._pause_action)

		icon = QIcon.fromTheme("media-skip-forward-symbolic.svg", style.standardIcon(QStyle.SP_MediaSkipForward))
		self._next_action = tool_bar.addAction(icon, "Next")
		self._next_action.triggered.connect(self.next_clicked)
		play_menu.addAction(self._next_action)

		icon = QIcon.fromTheme("media-playback-stop.png", style.standardIcon(QStyle.SP_MediaStop))
		self._stop_action = tool_bar.addAction(icon, "Stop")
		self._stop_action.triggered.connect(self._ensure_stopped)
		play_menu.addAction(self._stop_action)

		self.fullscreen = False  # Initially not in fullscreen mode

		# Create a QAction for toggling fullscreen
		self.fullscreen_action = QAction("Fullscreen", self)
		self.fullscreen_action.setShortcut("F11")
		self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
		self.addAction(self.fullscreen_action)


		self.menuBar().addAction(self.fullscreen_action)  # Add action to the menu bar

		# Create a QAction for mute
		icon_path = "no-sound.png"  # Relative path to the icon
		icon = QIcon(icon_path)
		self._mute_action = tool_bar.addAction(icon, "Mute")
		self._mute_action.setCheckable(True)  # Make it checkable for mute/unmute functionality
		self._mute_action.setChecked(False)  # Initial state is unmuted
		self._mute_action.triggered.connect(self.toggle_mute)
		tool_bar.addAction(self._mute_action)

		# Apply a style sheet to change appearance when checked
		tool_bar.setStyleSheet("""
			QToolBar QAction:checked {
				color: gray;  /* Change the text color to gray when checked */
			}
		""")
		
		self.media_player = QMediaPlayer()

		self._video_widget = QVideoWidget()
		self.setCentralWidget(self._video_widget)

		self._player.stateChanged.connect(self.update_buttons)
		self._player.setVideoOutput(self._video_widget)

		self._volume_slider = QSlider(Qt.Horizontal)
		self._volume_slider.setRange(0, 100)
		self._volume_slider.setValue(50)
		self._volume_slider.setTickInterval(10)
		self._volume_slider.setTickPosition(QSlider.TicksBelow)
		self._volume_slider.setToolTip("Volume")
		self._volume_slider.setFixedWidth(150)
		self._volume_slider.valueChanged.connect(self.set_volume)
		
		# Create a separator widget
		separator = QWidget()
		separator.setFixedWidth(10)  # Adjust the width as needed

		# Create a spacer item to push the volume slider to the right
		spacer = QWidget()
		spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

		# Add the spacer to the tool_bar
		tool_bar.addWidget(spacer)

		tool_bar.addWidget(self._volume_slider)
		
		# Create a vertical layout for the video and slider
		video_slider_layout = QVBoxLayout()

		# Add the video widget to the layout
		video_slider_layout.addWidget(self._video_widget)

		# Create a horizontal layout for the slider
		slider_layout = QHBoxLayout()
		slider_layout.addWidget(self._playback_time_label)  # Add the playback time label to the layout
		slider_layout.addWidget(self._slider)  # Add the slider to the layout
		slider_layout.addWidget(self._total_duration_label)  # Add the total duration label to the layout

		# Create the slider for controlling video position
		self._slider = SeekSlider(Qt.Horizontal)
		self._slider.setRange(0, 1000)
		self._slider.setValue(0)
		self._slider.sliderMoved.connect(self.set_position)
		self._slider.mousePressEvent = self.slider_mousePressEvent

		# Create a vertical layout for the video and slider
		video_slider_layout = QVBoxLayout()

		# Add the video widget to the layout
		video_slider_layout.addWidget(self._video_widget)

		# Create labels for displaying playback time and total duration
		self._playback_time_label = QLabel("0:00")
		self._total_duration_label = QLabel("0:00")

		# Create a horizontal layout for the slider and labels
		slider_layout = QHBoxLayout()
		slider_layout.addWidget(self._playback_time_label)
		slider_layout.addWidget(self._slider)
		slider_layout.addWidget(self._total_duration_label)

		# Add the slider layout to the vertical layout
		video_slider_layout.addLayout(slider_layout)

		# Create a widget for the video and slider layout
		video_slider_widget = QWidget()
		video_slider_widget.setLayout(video_slider_layout)

		# Set the video and slider widget as the central widget
		self.setCentralWidget(video_slider_widget)

		# Connect the sliderPressed signal to a custom slot
		self._slider.sliderPressed.connect(self.slider_pressed)

		# Connect the positionChanged and durationChanged signals to update labels
		self._player.positionChanged.connect(self.update_playback_time)
		self._player.durationChanged.connect(self.update_total_duration)
			 
		self.show()

	def closeEvent(self, event):
		if self._player.state() != QMediaPlayer.StoppedState:
			self._player.stop()
		
	def start_media_playback(self):
		if self._playlist_index >= 0:
			self._player.setMedia(QMediaContent(self._playlist[self._playlist_index]))
			self._player.play()
			
	def create_buffering_pipeline(self, media_url):
		# Create a GStreamer pipeline for buffering video
		pipeline = Gst.Pipeline.new("buffered-player")
		bus = pipeline.get_bus()

		# Create a GStreamer bus to handle media events
		bus.add_signal_watch()
		bus.connect("message::eos", self.handle_eos)
		bus.connect("message::error", self.handle_error)

		# Define the filesrc element
		filesrc = Gst.ElementFactory.make("filesrc", "file-source")
		filesrc.set_property("location", media_url)

		# Define the decodebin element
		decodebin = Gst.ElementFactory.make("decodebin", "decode-bin")

		# Create a GStreamer video sink element
		video_sink = Gst.ElementFactory.make("autovideosink", "video-sink")

		# Create a GStreamer audio sink element
		audio_sink = Gst.ElementFactory.make("autoaudiosink", "audio-sink")

		# Create a GStreamer video convert element
		video_convert = Gst.ElementFactory.make("videoconvert", "video-convert")

		# Create a GStreamer audio convert element
		audio_convert = Gst.ElementFactory.make("audioconvert", "audio-convert")

		# Create a GStreamer queue element for video buffering
		video_queue = Gst.ElementFactory.make("queue", "video-queue")
		video_queue.set_property("max-size-buffers", 0)  # Use 0 for an unlimited number of buffers
		video_queue.set_property("max-size-bytes", 5000000)  # 5MB

		# Create a GStreamer queue element for audio buffering
		audio_queue = Gst.ElementFactory.make("queue", "audio-queue")
		audio_queue.set_property("max-size-buffers", 0)  # Use 0 for an unlimited number of buffers
		audio_queue.set_property("max-size-bytes", 5000000)  # 5MB

		# Add GStreamer elements to the pipeline
		pipeline.add(filesrc)
		pipeline.add(decodebin)
		pipeline.add(video_queue)
		pipeline.add(video_convert)
		pipeline.add(video_sink)
		pipeline.add(audio_queue)
		pipeline.add(audio_convert)
		pipeline.add(audio_sink)

		# Link the GStreamer elements
		filesrc.link(decodebin)
		decodebin.connect("pad-added", self.on_pad_added)
		video_queue.link(video_convert)
		video_convert.link(video_sink)
		audio_queue.link(audio_convert)
		audio_convert.link(audio_sink)

		# Set the GStreamer pipeline to the "paused" state
		pipeline.set_state(Gst.State.PAUSED)

		return pipeline

	def open(self):
		self._ensure_stopped()
		file_dialog = QFileDialog(self)
		is_windows = sys.platform == 'win32'

		if not self._mime_types:
			self._mime_types = get_supported_mime_types()
		if is_windows:
			if AVI not in self._mime_types:
				self._mime_types.append(AVI)
		elif MP4 not in self._mime_types:
			self._mime_types.append(MP4)
		if TS not in self._mime_types:
			self._mime_types.append(TS)
		if FLV not in self._mime_types:
			self._mime_types.append(FLV)
		if _3GP not in self._mime_types:
			self._mime_types.append(_3GP)

		file_dialog.setMimeTypeFilters(self._mime_types)
		default_mimetype = AVI if is_windows else MP4

		if default_mimetype in self._mime_types:
			file_dialog.selectMimeTypeFilter(default_mimetype)

		movies_location = QStandardPaths.writableLocation(QStandardPaths.MoviesLocation)
		file_dialog.setDirectory(movies_location)

		if file_dialog.exec_() == QDialog.Accepted:
			url = file_dialog.selectedUrls()[0]
			file_name = url.fileName()  # Extract the file name from the URL
			self.setWindowTitle(f"{file_name} - Pot-O Video Player v0.1.0.1-alpha")  # Set window title
			self._playlist.append(url)
			self._playlist_index = len(self._playlist) - 1
			self._player.setMedia(QMediaContent(url))
			self._player.play()

	def _ensure_stopped(self):
		if self._player.state() != QMediaPlayer.StoppedState:
			self._player.stop()

	def previous_clicked(self):
		if self._player.position() <= 5000 and self._playlist_index > 0:
			self._playlist_index -= 1
			self._player.setMedia(QMediaContent(self._playlist[self._playlist_index]))
			self._player.play()
		else:
			self._player.setPosition(0)

	def next_clicked(self):
		if self._playlist_index < len(self._playlist) - 1:
			self._playlist_index += 1
			self._player.setMedia(QMediaContent(self._playlist[self._playlist_index]))
			self._player.play()
			
	def handle_eos(self, bus, message):
		# Handle End-of-Stream (EOS) message from GStreamer
		self.show_status_message("End of media")
		self._pipeline.set_state(Gst.State.NULL)

	def handle_error(self, bus, message):
		# Handle error messages from GStreamer
		error, debug_info = message.parse_error()
		self.show_status_message(f"Error: {error.message} - {debug_info if debug_info else 'No debug info'}")
		self._pipeline.set_state(Gst.State.NULL)

	def on_pad_added(self, decodebin, pad):
		# Handle dynamic pad linking when decoding begins
		pad_link = pad.get_current_caps()[0].get_name()
		if "video" in pad_link:
			pad.link(self._video_queue.get_static_pad("sink"))
		elif "audio" in pad_link:
			pad.link(self._audio_queue.get_static_pad("sink"))

	def set_position(self, new_position):
		# Calculate the actual video position based on the slider value
		video_duration = self._player.duration()
		video_position = 0  # Define video_position before the if statement
		if video_duration > 0:
			video_position = int(new_position * video_duration / 1000)
			# Capture the current position before seeking
			current_position = self._player.position()
			self._player.setPosition(video_position)
			
		# Check if the position did not change as expected
		if abs(self._player.position() - video_position) > 100:
			print("Buffering error detected. Resetting buffer.")
			self.reset_buffer()
			
			# Start the delay timer (e.g., 1000 milliseconds = 1 second)
			self._delay_timer.start(1000)
			
		 # Add a message handler for debugging
		self._bus.connect("message::error", self.on_error_message)
		self._bus.connect("message::warning", self.on_warning_message)
		
	def slider_mousePressEvent(self, event):
		new_value = event.x()  # You need to obtain new_value from the event
		self.set_position(new_value)
		
	# Add message handling functions
	def on_error_message(self, bus, message):
		error, debug_info = message.parse_error()
		print(f"Error: {error.message}", file=sys.stderr)
		if debug_info:
			print(f"Debug info: {debug_info}", file=sys.stderr)

	def on_warning_message(self, bus, message):
		warning, debug_info = message.parse_warning()
		print(f"Warning: {warning.message}", file=sys.stderr)
		if debug_info:
			print(f"Debug info: {debug_info}", file=sys.stderr)
			
	def reset_buffer(self):
		self._pipeline.set_state(Gst.State.NULL)
		self._pipeline.set_state(Gst.State.PAUSED)
		
		# After resetting, start the delay timer
		self._delay_timer.start(1000)

	def slider_mousePressEvent(self, event):
		# Calculate the position where the slider was clicked
		click_position = event.pos().x()

		# Calculate the value corresponding to the click position
		max_value = self._slider.maximum()
		new_value = int((click_position / self._slider.width()) * max_value)

		# Set the slider value and update the video position
		self._slider.setValue(new_value)
		self.set_position(new_value)

		# Call the base class method to handle other mouse press events
		super().mousePressEvent(event)

	def slider_pressed(self):
		click_position = QCursor.pos().x() - self._slider.mapToGlobal(QPoint(0, 0)).x()
		max_value = self._slider.maximum()
		new_value = int((click_position / self._slider.width()) * max_value)
		self._player.setPosition(new_value)

	@pyqtSlot()
	def reset_slider_position(self):
		if self._slider.total_duration > 0:
			self._slider.reset_position()  # Reset the slider handle position to zero

	def toggle_mute(self, checked):
		if checked:
			self._player.setMuted(True)
			self._mute_action.setIcon(QIcon.fromTheme("audio-volume-muted"))
		else:
			self._player.setMuted(False)
			self._mute_action.setIcon(QIcon.fromTheme("audio-volume-high"))

	def create_action(self, text, slot=None, shortcut=None):
		action = QAction(text, self)
		if slot is not None:
			action.triggered.connect(slot)
		if shortcut is not None:
			action.setShortcut(shortcut)
		return action

	def toggle_fullscreen(self):
		if not self.fullscreen:
			self.showFullScreen()
			self.menuBar().setVisible(False)  # Hide the menu bar in fullscreen mode
			self.tool_bar.setVisible(False)  # Hide the toolbar in fullscreen mode
			# Hide the QAction associated with icons in the toolbar
			self._play_action.setVisible(True)
			self._previous_action.setVisible(True)
			self._pause_action.setVisible(True)
			self._next_action.setVisible(True)
			self._stop_action.setVisible(True)
			self._mute_action.setVisible(True)
		else:
			self.showNormal()
			self.menuBar().setVisible(True)  # Show the menu bar in normal mode
			self.tool_bar.setVisible(True)  # Show the toolbar in normal mode
			# Show the QAction associated with icons in the toolbar
			self._play_action.setVisible(True)
			self._previous_action.setVisible(True)
			self._pause_action.setVisible(True)
			self._next_action.setVisible(True)
			self._stop_action.setVisible(True)
			self._mute_action.setVisible(True)

		self.fullscreen = not self.fullscreen  # Toggle fullscreen status


	def show_controls_overlay(self, show):
		if show:
			self.additional_controls_layout.setContentsMargins(10, 10, 10, 10)
			self.setCentralWidget(self._video_widget)
			self._video_widget.layout().addWidget(self.additional_controls)
		else:
			self._video_widget.layout().removeWidget(self.additional_controls)
			self.setCentralWidget(self._video_widget)

	def eventFilter(self, obj, event):
		if event.type() == QEvent.KeyPress and event.key() == Qt.Key_F11:
			self.toggle_fullscreen()
			return True  # Event handled
		elif event.type() == QEvent.Enter and obj == self._video_widget and self.fullscreen:
			self.show_controls_overlay(True)
		elif event.type() == QEvent.Leave and obj == self._video_widget and self.fullscreen:
			self.show_controls_overlay(False)
		return super().eventFilter(obj, event)

	def keyPressEvent(self, event):
		if event.key() == Qt.Key_F11:
			self.toggle_fullscreen()
		else:
			super().keyPressEvent(event)


	def set_volume(self, value):
		volume = value / 100.0
		self._player.setVolume(int(volume * 100))
		
	def time_thread(self):
		threading.Thread(target=self.update_time_).start()
	
	def update_total_duration(self, duration):
		# Update the total duration label with the new duration in hour:minutes:seconds format
		hours, remainder = divmod(duration // 1000, 3600)
		minutes, seconds = divmod(remainder, 60)
		self._total_duration_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
		
	def update_playback_time(self, position):
		if self._player.state() == QMediaPlayer.StoppedState:
			self._playback_time_label.setText("0:00:00")
		else:
			# Calculate hours, minutes, and seconds from the position in milliseconds
			total_seconds = position // 1000
			hours = total_seconds // 3600
			minutes = (total_seconds % 3600) // 60
			seconds = total_seconds % 60

			# Format the time as "hh:mm:ss"
			time_str = "{:02d}:{:02d}:{:02d}".format(hours, minutes, seconds)

			# Set the playback time label text
			self._playback_time_label.setText(time_str)
		
	def update_buttons(self, state):
		media_count = len(self._playlist)
		self._play_action.setEnabled(media_count > 0 and state != QMediaPlayer.PlayingState)
		self._pause_action.setEnabled(state == QMediaPlayer.PlayingState)
		self._stop_action.setEnabled(state != QMediaPlayer.StoppedState)
		self._previous_action.setEnabled(self._player.position() > 0)
		self._next_action.setEnabled(media_count > 1)
		
		# Update playback time label and total duration label
		duration = self._player.duration()  # Total duration in milliseconds
		current_position = self._player.position()  # Current position in milliseconds

		# Calculate total duration in the format "m:ss"
		total_minutes = duration // 60000
		total_seconds = (duration % 60000) // 1000
		total_duration_str = f"{total_minutes}:{total_seconds:02}"

		# Calculate current playback time in the format "m:ss"
		current_minutes = current_position // 60000
		current_seconds = (current_position % 60000) // 1000
		playback_time_str = f"{current_minutes}:{current_seconds:02}"

		self._playback_time_label.setText(playback_time_str)
		self._total_duration_label.setText(total_duration_str)

	def show_status_message(self, message):
		self.statusBar().showMessage(message, 5000)

	@pyqtSlot(QMediaPlayer.Error)
	def _player_error(self, error):
		error_string = self._player.errorString()
		print(error_string, file=sys.stderr)
		self.show_status_message(error_string)

if __name__ == '__main__':
	app = QApplication(sys.argv)
	main_win = MainWindow()
	app.setApplicationDisplayName("Pot-O Video Player v0.1.0.1-alpha")
	available_geometry = main_win.screen().availableGeometry()
	main_win.resize(int(available_geometry.width() / 1.5), int(available_geometry.height() / 1.3))
	main_win.show()
	sys.exit(app.exec_())
