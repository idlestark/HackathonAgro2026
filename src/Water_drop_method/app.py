import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.filedialog as fd
from PIL import Image, ImageTk
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import os
import cv2
import math
import statistics
import threading
import time
from typing import Optional
try:
    from .paths import get_hole_area_file, get_threshold_file, get_pump_timing_file, get_carousel_config_file
    from .camera_device import CameraOpenCV as cam
    from .data_acquisition import NIUSB6009 as dac, ArduinoUno
    from .pump_controller import PeristalticPump, list_serial_ports
    from .carousel_controller import CarouselController, RealTimeWearAnalyzer
    NIUSB6009 = dac
except ImportError:
    # Allows running this file directly during local debugging.
    from paths import get_hole_area_file, get_threshold_file, get_pump_timing_file, get_carousel_config_file
    from camera_device import CameraOpenCV as cam
    from data_acquisition import NIUSB6009 as dac, ArduinoUno
    from pump_controller import PeristalticPump, list_serial_ports
    from carousel_controller import CarouselController, RealTimeWearAnalyzer
    NIUSB6009 = dac


class WaterDropMethod:
    def __init__(self, root):
        self.root = root
        self.root.title("Water Drop Method")
        self.root.geometry("920x680")
        
        # Create notebook (tab container)
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Create the tabs
        self.camera_frame = ttk.Frame(self.notebook)
        self.threshold_frame = ttk.Frame(self.notebook)
        self.measurement_frame = ttk.Frame(self.notebook)
        self.pump_frame = ttk.Frame(self.notebook)
        self.carousel_frame = ttk.Frame(self.notebook)
        self.drop_energy_frame = ttk.Frame(self.notebook)
        self.video_processing_frame = ttk.Frame(self.notebook)
        self.help_frame = ttk.Frame(self.notebook)
        
        # Add tabs to notebook
        self.notebook.add(self.camera_frame, text="Camera")
        self.notebook.add(self.threshold_frame, text="Set Threshold")
        self.notebook.add(self.measurement_frame, text="Measurement")
        self.notebook.add(self.pump_frame, text="Pump Control")
        self.notebook.add(self.carousel_frame, text="Carousel (30)")
        self.notebook.add(self.drop_energy_frame, text="Drop Energy")
        self.notebook.add(self.video_processing_frame, text="Video Processing")
        self.notebook.add(self.help_frame, text="Help")
        
        # Peristaltic pump controller state (load saved defaults or 14 ms / 200 ms factory)
        self.default_pump_pulse, self.default_pump_interval = self.load_pump_timing_default()
        self.pump = PeristalticPump(pulse_ms=self.default_pump_pulse, interval_ms=self.default_pump_interval, drop_volume_ul=20.0)
        self.auto_pump_on_measurement = tk.BooleanVar(value=True)
        self.pump_ports_list = []

        # Carousel (30 aggregates) & Real-time wear state
        self.default_carousel_slots, self.default_carousel_steps = self.load_carousel_config_default()
        self.carousel = CarouselController(
            total_slots=self.default_carousel_slots,
            steps_per_slot=self.default_carousel_steps,
            motor_mode="STEPPER_28BYJ48",
        )
        self.realtime_wear_enabled = tk.BooleanVar(value=True)
        self.auto_carousel_on_rupture = tk.BooleanVar(value=True)
        self.share_pump_serial_var = tk.BooleanVar(value=True)
        self.wear_analyzer = RealTimeWearAnalyzer(hole_area_px=float(self.load_hole_area_default() or 4000))
        self.latest_wear_info = None
        self.sample_broken_in_realtime = False

        # Setup Camera tab
        self.setup_camera_tab()
        
        # Setup Threshold tab
        self.setup_threshold_tab()

        # Setup Measurement tab
        self.setup_measurement_tab()

        # Setup Pump Control tab
        self.setup_pump_tab()

        # Setup Carousel (30 aggregates) tab
        self.setup_carousel_tab()
        
        # Setup Drop energy tab
        self.setup_drop_energy_tab()
        
        # Setup Video processing tab
        self.setup_video_proc_tab()

        # Setup Help tab
        self.setup_help_tab()

        # Bind window close event for clean shutdown
        self.root.protocol("WM_DELETE_WINDOW", self.on_app_close)
        
        # Global camera variable
        self.camera = None
        
        # Variable to store threshold value
        self.threshold_value = None

        # Variable indicating measurement in progress
        self.is_measuring = False

        # Canvas to display the image and draw the hole area
        self.canvas_hole_area = None
        self.selected_image_hole_area = None

        # Frame display the video video for hole area selection
        self.video_label_hole_area = None

        # Widgets created dynamically in Video Processing tab
        self.slider = None
        self.hole_area_confirm_button = None
#Ends the mainwindow definitions

#STARTS THE TABS DEFINITIONS
# Setup the camera tab
    def setup_camera_tab(self):
        # Create a frame for buttons
        camera_buttons_frame = ttk.Frame(self.camera_frame)
        camera_buttons_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Add buttons
        start_preview_button = ttk.Button(
            camera_buttons_frame,
            text='Start Preview',
            command=self.start_preview
        )
        start_preview_button.pack(pady=5)
        
        stop_preview_button = ttk.Button(
            camera_buttons_frame,
            text='Stop Preview',
            command=self.stop_preview
        )
        stop_preview_button.pack(pady=5)

        # Add device selection dropdown
        device_frame = ttk.Frame(camera_buttons_frame)
        device_frame.pack(pady=5)
        
        device_label = ttk.Label(device_frame, text="Camera Device:")
        device_label.pack(side=tk.TOP)
        
        self.device_var = tk.StringVar(value="0")
        self.device_combo = ttk.Combobox(
            device_frame,
            textvariable=self.device_var,
            values=["0", "1", "2"],
            width=5,
            state="readonly"
        )
        self.device_combo.pack(side=tk.TOP)
        
        # Create a frame for the preview image
        self.preview_frame = ttk.Frame(self.camera_frame)
        self.preview_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Create a label to display the camera preview
        self.preview_label = ttk.Label(self.preview_frame)
        self.preview_label.pack(fill=tk.BOTH, expand=True)

# Setup the threshold tab    
    def setup_threshold_tab(self):
        # Create a frame for controls
        threshold_controls_frame = ttk.Frame(self.threshold_frame)
        threshold_controls_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Add DAC selection dropdown
        DAC_frame_threshold = ttk.Frame(threshold_controls_frame)
        DAC_frame_threshold.pack(pady=5)
        
        DAC_label_threshold = ttk.Label(DAC_frame_threshold, text="DAC Device:")
        DAC_label_threshold.pack(side=tk.TOP)
        
        self.DAC_var_threshold = tk.StringVar(value="Test")
        self.DAC_combo_threshold = ttk.Combobox(
            DAC_frame_threshold,
            textvariable=self.DAC_var_threshold,
            values=["Test", "NIUSB6009", "ArduinoUno"],
            width=12,
            state="readonly"
        )
        self.DAC_combo_threshold.pack(side=tk.TOP)

        # Add label and input for number of measures
        measures_label = ttk.Label(
            threshold_controls_frame,
            text='Number of measures'
        )
        measures_label.pack(pady=(0, 5))
        
        self.measures_var = tk.StringVar(value="5000")
        self.measures_input = ttk.Entry(
            threshold_controls_frame,
            textvariable=self.measures_var
        )
        self.measures_input.pack(pady=(0, 5), fill=tk.X)
        
        # Add set threshold button
        set_threshold_button = ttk.Button(
            threshold_controls_frame,
            text='Set Threshold',
            command=self.set_threshold
        )
        set_threshold_button.pack(pady=5)
        
        # Add confirmation buttons for threshold
        self.confirm_frame = ttk.Frame(threshold_controls_frame)
        self.confirm_frame.pack(pady=5, fill=tk.X)
        
        # Use a dedicated name to avoid conflicts with other tabs
        self.threshold_confirm_button = ttk.Button(
            self.confirm_frame,
            text='Confirm Threshold',
            command=self.confirm_threshold,
            state=tk.DISABLED
        )
        self.threshold_confirm_button.pack(side=tk.LEFT, padx=2)
        
        # Create a frame for the threshold plot
        self.threshold_plot_frame = ttk.Frame(self.threshold_frame)
        self.threshold_plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

# Setup the measurement tab
    def setup_measurement_tab(self):
        # Create a frame for controls
        measurement_controls_frame = ttk.Frame(self.measurement_frame)
        measurement_controls_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Add camera selection dropdown
        device_frame_measure = ttk.Frame(measurement_controls_frame)
        device_frame_measure.pack(pady=5)
        
        device_label = ttk.Label(device_frame_measure, text="Camera Device:")
        device_label.pack(side=tk.TOP)
        
        self.device_var_measure = tk.StringVar(value="0")
        self.device_combo_measure = ttk.Combobox(
            device_frame_measure,
            textvariable=self.device_var_measure,
            values=["0", "1", "2"],
            width=5,
            state="readonly"
        )
        self.device_combo_measure.pack(side=tk.TOP)
        
        # Add DAC selection dropdown
        DAC_frame_measure = ttk.Frame(measurement_controls_frame)
        DAC_frame_measure.pack(pady=5)
        
        DAC_label = ttk.Label(DAC_frame_measure, text="DAC Device:")
        DAC_label.pack(side=tk.TOP)
        
        self.DAC_var_measure = tk.StringVar(value="Test")
        self.DAC_combo_measure = ttk.Combobox(
            DAC_frame_measure,
            textvariable=self.DAC_var_measure,
            values=["Test", "NIUSB6009", "ArduinoUno"],
            width=12,
            state="readonly"
        )
        self.DAC_combo_measure.pack(side=tk.TOP)
        
        # Add label and input for number of drops
        measures_drops_label = ttk.Label(
            measurement_controls_frame,
            text='Number of drops'
        )
        measures_drops_label.pack(pady=(0, 5))
        
        self.measures_drops = tk.StringVar(value="500")
        self.measures_drops_input = ttk.Entry(
            measurement_controls_frame,
            textvariable=self.measures_drops
        )
        self.measures_drops_input.pack(pady=(0, 5), fill=tk.X)

        # Add label and input for number of previous frames
        measures_frames_label = ttk.Label(
            measurement_controls_frame,
            text='Number of previous frames'
        )
        measures_frames_label.pack(pady=(0, 5))
        
        self.measures_frames = tk.StringVar(value="20")
        self.measures_frames_input = ttk.Entry(
            measurement_controls_frame,
            textvariable=self.measures_frames
        )
        self.measures_frames_input.pack(pady=(0, 5), fill=tk.X)

        # Add Save file button
        self.save_file_button = ttk.Button(
            measurement_controls_frame,
            text='Save File As',
            command=self.save_file_as
        )
        self.save_file_button.pack(pady=5)

        # Add Start Measurement button
        self.start_measurement_button = ttk.Button(
            measurement_controls_frame,
            text='Start Measurement',
            command=self.start_measurement,
            state=tk.DISABLED  # Initially disabled
        )
        self.start_measurement_button.pack(pady=5)

        # Add Stop Measurement button
        self.stop_measurement_button = ttk.Button(
            measurement_controls_frame,
            text='Stop Measurement',
            command=self.stop_measurement,
            state=tk.DISABLED  # Initially disabled
        )
        self.stop_measurement_button.pack(pady=5)

        # ---- Real-Time Wear & Carousel Automation Panel ----
        rt_group = ttk.LabelFrame(measurement_controls_frame, text=" Real-Time Wear & Carousel ", padding=6)
        rt_group.pack(fill=tk.X, pady=(8, 4))

        rt_check = ttk.Checkbutton(
            rt_group,
            text="Real-time wear (gota a gota)",
            variable=self.realtime_wear_enabled
        )
        rt_check.pack(anchor="w", pady=2)

        hole_row = ttk.Frame(rt_group)
        hole_row.pack(fill=tk.X, pady=2)
        ttk.Label(hole_row, text="Orifice As (px²):").pack(side=tk.LEFT)
        self.realtime_hole_area_var = tk.StringVar(value=str(self.load_hole_area_default() or 4000))
        ttk.Entry(hole_row, textvariable=self.realtime_hole_area_var, width=7, justify="center").pack(side=tk.RIGHT)

        carousel_auto_check = ttk.Checkbutton(
            rt_group,
            text="Auto-rotate Carousel on rupture",
            variable=self.auto_carousel_on_rupture
        )
        carousel_auto_check.pack(anchor="w", pady=2)

        samples_row = ttk.Frame(rt_group)
        samples_row.pack(fill=tk.X, pady=2)
        ttk.Label(samples_row, text="Samples (1-30):").pack(side=tk.LEFT)
        self.batch_samples_var = tk.StringVar(value="30")
        ttk.Spinbox(
            samples_row, from_=1, to=30, textvariable=self.batch_samples_var, width=5, justify="center"
        ).pack(side=tk.RIGHT)

        # Add Tutorial / Workflow button
        self.workflow_tutorial_button = ttk.Button(
            measurement_controls_frame,
            text='📖 Tutorial: Paso a Paso',
            command=self.show_measurement_tutorial
        )
        self.workflow_tutorial_button.pack(pady=(8, 5), fill=tk.X)

        # Create a frame for the measurement
        measured_drops_frame = ttk.Frame(self.measurement_frame, padding=10)
        measured_drops_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Add label output for number of drops registered
        self.measured_drops_label = ttk.Label(
            measured_drops_frame,
            text='Number of drops registered: ' + str(0),
            font=("Segoe UI", 12, "bold")
        )
        self.measured_drops_label.pack(pady=(10, 4))

        self.realtime_slot_label = ttk.Label(
            measured_drops_frame,
            text="Carousel Slot: 1 / 30 | Laser Reader: ALIGNED",
            font=("Segoe UI", 10, "bold"),
            foreground="#0284c7"
        )
        self.realtime_slot_label.pack(pady=2)

        self.realtime_wear_label = ttk.Label(
            measured_drops_frame,
            text="Real-Time Normalized Area (Ac-As)/(Ai-As): 1.000 | Wear: 0.0%",
            font=("Segoe UI", 10)
        )
        self.realtime_wear_label.pack(pady=4)

        self.realtime_wear_var = tk.DoubleVar(value=0.0)
        self.realtime_wear_progressbar = ttk.Progressbar(
            measured_drops_frame, variable=self.realtime_wear_var, maximum=100.0
        )
        self.realtime_wear_progressbar.pack(fill=tk.X, padx=20, pady=4)

        self.realtime_status_banner = ttk.Label(
            measured_drops_frame,
            text="Status: Waiting to start measurement...",
            font=("Segoe UI", 9, "bold"),
            foreground="#475569"
        )
        self.realtime_status_banner.pack(pady=4)

        # Live ROI contour preview frame
        roi_frame = ttk.LabelFrame(measured_drops_frame, text=" Real-Time Drop-by-Drop Aggregate Contour (Ac) ", padding=6)
        roi_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        self.realtime_preview_label = ttk.Label(roi_frame, anchor="center", text="Live contour preview appears here during drop impacts")
        self.realtime_preview_label.pack(fill=tk.BOTH, expand=True)

#Setup the drop energy tab
    def setup_drop_energy_tab(self):
        # Create a frame for controls
        drop_energy_controls_frame = ttk.Frame(self.drop_energy_frame)
        drop_energy_controls_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        # Add label and input for Drop weight
        drops_weight_label = ttk.Label(
            drop_energy_controls_frame,
            text='Drop weight (mg)'
        )
        drops_weight_label.pack(pady=(0, 5))

        self.drops_weight = tk.StringVar(value="20.90395")
        self.drop_weight_input = ttk.Entry(
            drop_energy_controls_frame,
            textvariable=self.drops_weight
        )
        self.drop_weight_input.pack(pady=(0, 5), fill=tk.X)

        # Add label and input for Water density
        water_density_label = ttk.Label(
            drop_energy_controls_frame,
            text='Water density (kg)'
        )
        water_density_label.pack(pady=(0, 5))

        self.water_density = tk.StringVar(value="1000.0")
        self.water_density_input = ttk.Entry(
            drop_energy_controls_frame,
            textvariable=self.water_density
        )
        self.water_density_input.pack(pady=(0, 5), fill=tk.X)

        # Add label and input for Air density
        air_density_label = ttk.Label(
            drop_energy_controls_frame,
            text='Air density (kg)'
        )
        air_density_label.pack(pady=(0, 5))

        self.air_density = tk.StringVar(value="1.225")  
        self.air_density_input = ttk.Entry(
            drop_energy_controls_frame,
            textvariable=self.air_density
        )
        self.air_density_input.pack(pady=(0, 5), fill=tk.X)

        # Add label and input for Drag coefficient
        drag_coefficient_label = ttk.Label(
            drop_energy_controls_frame,
            text='Drag coefficient'
        )
        drag_coefficient_label.pack(pady=(0, 5))

        self.drag_coefficient = tk.StringVar(value="0.5207")  
        self.drag_coefficient_input = ttk.Entry(
            drop_energy_controls_frame,
            textvariable=self.drag_coefficient
        )
        self.drag_coefficient_input.pack(pady=(0, 5), fill=tk.X)

        # Add label and input for Drop height
        drop_height_label = ttk.Label(
            drop_energy_controls_frame,
            text='Drop height (cm)'
        )
        drop_height_label.pack(pady=(0, 5))

        self.drop_height = tk.StringVar(value="53")  
        self.drop_height_input = ttk.Entry(
            drop_energy_controls_frame,
            textvariable=self.drop_height
        )
        self.drop_height_input.pack(pady=(0, 5), fill=tk.X)

        # Add Start simulation button
        self.start_simulation_button = ttk.Button(
            drop_energy_controls_frame,
            text='Start Simulation',
            command=self.start_simulation
        )
        self.start_simulation_button.pack(pady=5)

        # Create a frame for the threshold plot
        self.simulation_plot_frame = ttk.Frame(self.drop_energy_frame)
        self.simulation_plot_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

# Setup the video processing tab
    def setup_video_proc_tab(self):
        # Create a frame for video processing controls
        video_proc_controls_frame = ttk.Frame(self.video_processing_frame)
        video_proc_controls_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        # Add Load Videos Folder button
        self.load_video_button = ttk.Button(
            video_proc_controls_frame,
            text='Load Videos Folder',
            command=self.load_video_folder
        )
        self.load_video_button.pack(pady=(0,15))
        


        # Add label, check and input for hole area
        hole_area_label = ttk.Label(
            video_proc_controls_frame,
            text='Hole Area (px^2)'
        )
        hole_area_label.pack(pady=(0, 5))

        # Create frame for input and check hole area controls
        hole_area_frame = ttk.Frame(video_proc_controls_frame)
        hole_area_frame.pack(pady=(0, 5))

        # Add input for hole area (load saved default if available)
        default_hole_area = self.load_hole_area_default() or 4000
        self.hole_area = tk.IntVar(value=default_hole_area)  # Use IntVar for numeric input
        self.hole_area_input = ttk.Entry(
            hole_area_frame,
            textvariable=self.hole_area,
            justify='center',
            width=8,
            state='disabled'  # Initially disabled
        )
        self.hole_area_input.pack(side=tk.LEFT, pady=(0, 5))

        check_var = tk.IntVar()
        self.hole_area_check = ttk.Checkbutton(
            hole_area_frame,
            text='Use this, or...',
            command= self.check_action,
            variable=check_var,  # Use IntVar for checkbox state
            state='disabled'  # Initially disabled
        )
        self.hole_area_check.pack(side=tk.RIGHT, pady=(0, 5))

        #Add label and drop down for Select video to set hole area
        self.set_hole_area_label = ttk.Label(
            video_proc_controls_frame,
            text='Select video to set hole area'
        )
        self.set_hole_area_label.pack(pady=(0, 5))

        self.video_selection = tk.StringVar()
        self.video_selection_dropdown = ttk.Combobox(
            video_proc_controls_frame,
            textvariable=self.video_selection,
            state= 'disabled' # Initially disabled
        )
        self.video_selection_dropdown.pack(pady=(0, 5))

        # Enable processing when a video is selected
        self.video_selection_dropdown.bind(
            "<<ComboboxSelected>>",
            lambda event: self.process_videos_button.config(state=tk.NORMAL)
            )

        # Add process video button
        self.process_videos_button = ttk.Button(
            video_proc_controls_frame,
            text='Process Videos',
            command=self.process_videos
        )
        self.process_videos_button.pack(pady=(0, 5))
        self.process_videos_button.config(state=tk.DISABLED)  # Initially disabled


        # Create a frame for the video processing output
        self.video_output_frame = ttk.Frame(self.video_processing_frame)
        self.video_output_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

# Setup the help tab
    def setup_help_tab(self):
        self.help_sections = [
            (
                "overview",
                "Quick Start",
                {
                    "intro": "Use this tab as the guided map for the whole app. Start with Camera, continue with Set Threshold, then Measurement, and finish with Drop Energy or Video Processing depending on what you need.",
                    "cards": [
                        {
                            "title": "Recommended flow",
                            "items": [
                                "1. Open Camera and verify framing before capturing data.",
                                "2. Set Threshold to store the photodiode cutoff used by Measurement.",
                                "3. Run Measurement to record drops and save the video file.",
                                "4. Use Drop Energy for the physical simulation of drop fall and drop energy determination.",
                                "5. Video Processing for batch analysis and determination of median drop value for aggregate breakdown.",
                            ],
                        },
                        {
                            "title": "What this app keeps for you",
                            "items": [
                                "Threshold and hole area values are stored in the user state folder.",
                                "The Measurement tab reuses the saved threshold automatically.",
                                "Video Processing can reuse a typed hole area or a selected ellipse from a frame.",
                            ],
                        },
                    ],
                    "tips": [
                        "If a control is disabled, check whether the previous step was completed first.",
                        "The left navigation lets you jump directly to the help for each tab.",
                    ],
                },
            ),
            (
                "camera",
                "Camera",
                {
                    "intro": "Preview the live camera feed and confirm that the scene is aligned before starting any measurement workflow.",
                    "cards": [
                        {
                            "title": "Main actions",
                            "items": [
                                "Select the camera device from the dropdown.",
                                "Press Start Preview to open the live feed.",
                                "Press Stop Preview when you are done or before switching workflows.",
                            ],
                        },
                        {
                            "title": "Good practice",
                            "items": [
                                "Keep the sample centered and stable while checking the preview.",
                                "Stop the preview before moving to thresholding or measurement if the camera is still active.",
                            ],
                        },
                    ],
                    "tips": [
                        "If the preview looks frozen, stop it and start it again with the correct device.",
                    ],
                },
            ),
            (
                "threshold",
                "Set Threshold",
                {
                    "intro": "Capture photodiode samples, click the plot to choose the threshold, and confirm it so the value is saved for later measurements.",
                    "cards": [
                        {
                            "title": "Main actions",
                            "items": [
                                "Choose the DAC device: Test, NIUSB6009 or ArduinoUno.",
                                "Enter the number of measures to collect.",
                                "Click Set Threshold to build the plot.",
                                "Click on the graph to place the red threshold line and then confirm it.",
                            ],
                        },
                        {
                            "title": "Result",
                            "items": [
                                "The selected threshold is written to the persistent threshold file.",
                                "Measurement reads this stored value automatically.",
                            ],
                        },
                    ],
                    "tips": [
                        "Use the Test source when you want to explore the workflow without hardware.",
                    ],
                },
            ),
            (
                "measurement",
                "Measurement",
                {
                    "intro": "Record the drop events after the threshold is defined, while the app counts detections and writes the capture video.",
                    "cards": [
                        {
                            "title": "Main actions",
                            "items": [
                                "Choose the camera and DAC devices.",
                                "Set the number of drops to record and the number of previous frames.",
                                "Use Save File As to choose the output video path.",
                                "Start Measurement to begin the acquisition loop and use Stop Measurement to interrupt it.",
                            ],
                        },
                        {
                            "title": "How it behaves",
                            "items": [
                                "The app collects initial frames first, then waits for the drop event.",
                                "Each detection updates the counter shown on the right.",
                                "The saved threshold must exist before measurement starts.",
                                "If enabled in Pump Control, the peristaltic pump auto-starts when measurement begins.",
                            ],
                        },
                    ],
                    "tips": [
                        "If Start Measurement stays disabled, first choose an output file with Save File As.",
                    ],
                },
            ),
            (
                "pump",
                "Pump Control",
                {
                    "intro": "Configure, calibrate, and operate the 12V peristaltic pump replacing the Mariotte tube.",
                    "cards": [
                        {
                            "title": "Main actions",
                            "items": [
                                "Select the Serial Port (or Simulation) and click Connect.",
                                "Adjust pulse duration (volume) and interval (cadence), or click 'Set Target 6.0 mL/min'.",
                                "Click 'Apply to Pump' to update microcontroller parameters on the fly.",
                                "Use 'Deliver 1 Drop' to prime the needle, and 'Start/Stop Pump' to run continuously.",
                            ],
                        },
                        {
                            "title": "Measurement Integration",
                            "items": [
                                "Enable 'Auto-start pump on Start Measurement' to coordinate drop generation with capture.",
                            ],
                        },
                    ],
                    "tips": [
                        "Use 'Simulation' port if exploring the UI without an Arduino/ESP32 connected.",
                        "Standard target 6.0 mL/min = ~5 drops/sec (14 ms pulse + 186 ms interval).",
                    ],
                },
            ),
            (
                "carousel",
                "Carousel (30)",
                {
                    "intro": "Operate the 30-aggregate rotating disc driven by a 28BYJ-48 stepper motor (ULN2003) and/or DC motor (H-bridge) with an optical Laser Reader on ESP32/Arduino.",
                    "cards": [
                        {
                            "title": "Main actions",
                            "items": [
                                "Connect to the ESP32/Arduino port (or share connection with Pump / use Simulation).",
                                "Use Home (Slot 1), Next, Prev, or Go to Slot to position any of the 30 soil aggregates under the needle.",
                                "Verify sub-millimetric alignment with the Laser Reader indicator.",
                                "Inspect the 30-slot status matrix and export the batch results table.",
                            ],
                        },
                        {
                            "title": "Real-Time Drop-by-Drop Automation",
                            "items": [
                                "During Measurement, the camera calculates normalized aggregate area (Ac - As) / (Ai - As) on every drop.",
                                "When Normalized Area <= 0 (sample broken/disintegrated), the pump pauses, the carousel rotates to the next slot with laser confirmation, and measurement resumes automatically.",
                            ],
                        },
                    ],
                    "tips": [
                        "Supports are separated > 3.5 cm on a 33.4 cm diameter disc with splash guards to prevent the 3 cm drop splash radius from wetting adjacent samples.",
                    ],
                },
            ),
            (
                "drop_energy",
                "Drop Energy",
                {
                    "intro": "Estimate the velocity curve and impact energy from the physical parameters of the drop and the environment.",
                    "cards": [
                        {
                            "title": "Main inputs",
                            "items": [
                                "Drop weight in mg.",
                                "Water density and air density.",
                                "Drag coefficient.",
                                "Drop height in cm.",
                            ],
                        },
                        {
                            "title": "Output",
                            "items": [
                                "Press Start Simulation to render the velocity curve.",
                                "The title shows the estimated drop energy in mJ.",
                            ],
                        },
                    ],
                    "tips": [
                        "If you are comparing scenarios, change one value at a time so the curve is easier to interpret.",
                    ],
                },
            ),
            (
                "video_processing",
                "Video Processing",
                {
                    "intro": "Batch-process videos to measure the normalized area over time, either by selecting the hole ellipse manually or by typing its area directly.",
                    "cards": [
                        {
                            "title": "Main actions",
                            "items": [
                                "Load Videos Folder to read the video list.",
                                "Choose a video when you want to draw the hole ellipse from a frame.",
                                "Use the hole area input and checkbox if you want to skip manual selection.",
                                "Press Process Videos to generate the plots and outputs.",
                            ],
                        },
                        {
                            "title": "Manual selection",
                            "items": [
                                "Move the slider to locate a representative frame.",
                                "Confirm the frame, adjust the ellipse, and then confirm the ellipse.",
                                "The selected area is saved for future sessions.",
                            ],
                        },
                    ],
                    "tips": [
                        "The Cancel button is available while batch processing is running.",
                        "If you already know the hole area, the checkbox is the fastest path.",
                    ],
                },
            ),
        ]
        self.help_section_lookup = {key: {"title": title, **payload} for key, title, payload in self.help_sections}
        self.help_selected_key = None

        help_outer = tk.Frame(self.help_frame, bg="#eef4fb")
        help_outer.pack(fill=tk.BOTH, expand=True)

        left_panel = tk.Frame(help_outer, bg="#17324d", width=260)
        left_panel.pack(side=tk.LEFT, fill=tk.Y)
        left_panel.pack_propagate(False)

        title_label = tk.Label(
            left_panel,
            text="Help",
            bg="#17324d",
            fg="white",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        )
        title_label.pack(fill=tk.X, padx=18, pady=(18, 4))

        subtitle_label = tk.Label(
            left_panel,
            text="Choose a tab to see what it does and how to use it.",
            bg="#17324d",
            fg="#d6e4f5",
            wraplength=220,
            justify=tk.LEFT,
            anchor="w",
        )
        subtitle_label.pack(fill=tk.X, padx=18, pady=(0, 12))
        self._bind_help_wrap(subtitle_label, left_panel, horizontal_padding=40, min_wrap=140)

        nav_label = tk.Label(
            left_panel,
            text="Navigate",
            bg="#17324d",
            fg="#8fb3d9",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        nav_label.pack(fill=tk.X, padx=18, pady=(0, 8))

        nav_container = tk.Frame(left_panel, bg="#17324d")
        nav_container.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self.help_nav_buttons = {}
        for key, title, _ in self.help_sections:
            button = tk.Button(
                nav_container,
                text=title,
                command=lambda section_key=key: self.show_help_section(section_key),
                anchor="w",
                justify=tk.LEFT,
                relief=tk.FLAT,
                bd=0,
                padx=14,
                pady=10,
                bg="#edf2f7",
                fg="#17324d",
                activebackground="#dbeafe",
                activeforeground="#0f172a",
                highlightthickness=0,
                font=("Segoe UI", 10, "bold"),
            )
            button.pack(fill=tk.X, pady=4)
            self.help_nav_buttons[key] = button

        footer_label = tk.Label(
            left_panel,
            text="The help panel stays inside the app, so you can switch tabs without losing context.",
            bg="#17324d",
            fg="#a7bed6",
            wraplength=220,
            justify=tk.LEFT,
            anchor="w",
            font=("Segoe UI", 9),
        )
        footer_label.pack(fill=tk.X, padx=18, pady=(0, 18))
        self._bind_help_wrap(footer_label, left_panel, horizontal_padding=40, min_wrap=140)

        right_panel = tk.Frame(help_outer, bg="#f8fafc")
        right_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.help_canvas = tk.Canvas(right_panel, bg="#f8fafc", highlightthickness=0)
        help_scrollbar = ttk.Scrollbar(right_panel, orient=tk.VERTICAL, command=self.help_canvas.yview)
        self.help_canvas.configure(yscrollcommand=help_scrollbar.set)
        help_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.help_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.help_content_host = tk.Frame(self.help_canvas, bg="#f8fafc")
        self.help_content_window = self.help_canvas.create_window((0, 0), window=self.help_content_host, anchor="nw")

        def _sync_help_scrollregion(event):
            self.help_canvas.configure(scrollregion=self.help_canvas.bbox("all"))

        def _sync_help_width(event):
            self.help_canvas.itemconfigure(self.help_content_window, width=event.width)

        self.help_content_host.bind("<Configure>", _sync_help_scrollregion)
        self.help_canvas.bind("<Configure>", _sync_help_width)
        self.root.bind_all("<MouseWheel>", self._on_help_mousewheel, add="+")
        self.root.bind_all("<Button-4>", self._on_help_mousewheel, add="+")
        self.root.bind_all("<Button-5>", self._on_help_mousewheel, add="+")

        self.show_help_section("overview")

    def show_help_section(self, section_key):
        section = self.help_section_lookup[section_key]
        self.help_selected_key = section_key

        for widget in self.help_content_host.winfo_children():
            widget.destroy()

        for key, button in self.help_nav_buttons.items():
            if key == section_key:
                button.configure(bg="#2563eb", fg="white", activebackground="#1d4ed8", activeforeground="white")
            else:
                button.configure(bg="#edf2f7", fg="#17324d", activebackground="#dbeafe", activeforeground="#0f172a")

        header_card = tk.Frame(self.help_content_host, bg="white", bd=1, relief=tk.SOLID)
        header_card.pack(fill=tk.X, padx=20, pady=(20, 12))

        header_title = tk.Label(
            header_card,
            text=section["title"],
            bg="white",
            fg="#0f172a",
            font=("Segoe UI", 20, "bold"),
            anchor="w",
            justify=tk.LEFT,
            wraplength=560,
        )
        header_title.pack(fill=tk.X, padx=20, pady=(16, 6))
        self._bind_help_wrap(header_title, header_card, horizontal_padding=48, min_wrap=180)

        header_intro = tk.Label(
            header_card,
            text=section["intro"],
            bg="white",
            fg="#334155",
            font=("Segoe UI", 11),
            wraplength=620,
            justify=tk.LEFT,
            anchor="w",
        )
        header_intro.pack(fill=tk.X, padx=20, pady=(0, 16))
        self._bind_help_wrap(header_intro, header_card, horizontal_padding=48, min_wrap=200)

        body_frame = tk.Frame(self.help_content_host, bg="#f8fafc")
        body_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))

        for card in section["cards"]:
            self._create_help_card(body_frame, card["title"], card["items"])

        tips_card = tk.Frame(body_frame, bg="#eff6ff", bd=1, relief=tk.SOLID)
        tips_card.pack(fill=tk.X, pady=(0, 14))

        tips_title = tk.Label(
            tips_card,
            text="Tips",
            bg="#eff6ff",
            fg="#1d4ed8",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        )
        tips_title.pack(fill=tk.X, padx=16, pady=(12, 4))

        for tip in section["tips"]:
            tip_label = tk.Label(
                tips_card,
                text=f"• {tip}",
                bg="#eff6ff",
                fg="#1e293b",
                wraplength=620,
                justify=tk.LEFT,
                anchor="w",
                font=("Segoe UI", 10),
            )
            tip_label.pack(fill=tk.X, padx=16, pady=(0, 10))
            self._bind_help_wrap(tip_label, tips_card, horizontal_padding=40, min_wrap=200)

    def _create_help_card(self, parent, title, items):
        card = tk.Frame(parent, bg="white", bd=1, relief=tk.SOLID)
        card.pack(fill=tk.X, pady=(0, 14))

        card_title = tk.Label(
            card,
            text=title,
            bg="white",
            fg="#0f172a",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
        )
        card_title.pack(fill=tk.X, padx=16, pady=(12, 6))

        for item in items:
            item_label = tk.Label(
                card,
                text=f"• {item}",
                bg="white",
                fg="#334155",
                wraplength=620,
                justify=tk.LEFT,
                anchor="w",
                font=("Segoe UI", 10),
            )
            item_label.pack(fill=tk.X, padx=16, pady=(0, 8))
            self._bind_help_wrap(item_label, card, horizontal_padding=40, min_wrap=200)

    def _bind_help_wrap(self, label, container, horizontal_padding=32, min_wrap=180):
        """Keep help text wrapped to the visible card width."""
        def _update_wrap(event=None):
            width = container.winfo_width()
            if event is not None and getattr(event, "width", 0) > 0:
                width = event.width
            if width <= 1:
                return
            label.configure(wraplength=max(min_wrap, width - horizontal_padding))

        container.bind("<Configure>", _update_wrap, add="+")
        self.root.after(0, _update_wrap)

    def _on_help_mousewheel(self, event):
        """Scroll Help content with mouse wheel when pointer is over the Help panel."""
        if self.notebook.select() != str(self.help_frame):
            return

        hovered_widget = self.root.winfo_containing(event.x_root, event.y_root)
        if hovered_widget is None:
            return
        if not self._is_descendant_widget(hovered_widget, self.help_canvas):
            return

        if getattr(event, "num", None) == 4:
            step = -1
        elif getattr(event, "num", None) == 5:
            step = 1
        else:
            if event.delta == 0:
                return
            step = -1 if event.delta > 0 else 1

        self.help_canvas.yview_scroll(step, "units")
        return "break"

    def _is_descendant_widget(self, widget, ancestor):
        """Return True if widget is ancestor or contained by ancestor."""
        current = widget
        while current is not None:
            if current == ancestor:
                return True
            parent_name = current.winfo_parent()
            if not parent_name:
                break
            try:
                current = current.nametowidget(parent_name)
            except Exception:
                break
        return False

    # Setup the peristaltic pump tab
    def setup_pump_tab(self):
        container = ttk.Frame(self.pump_frame, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        left_col = ttk.Frame(container)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        right_col = ttk.Frame(container)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # ---- Connection Group ----
        conn_group = ttk.LabelFrame(left_col, text=" Hardware Connection (MOSFET / Arduino / ESP32) ", padding=10)
        conn_group.pack(fill=tk.X, pady=(0, 10))

        port_row = ttk.Frame(conn_group)
        port_row.pack(fill=tk.X, pady=4)
        ttk.Label(port_row, text="Serial Port:").pack(side=tk.LEFT, padx=(0, 8))

        self.pump_port_var = tk.StringVar()
        self.pump_port_combo = ttk.Combobox(port_row, textvariable=self.pump_port_var, state="readonly", width=24)
        self.pump_port_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        refresh_btn = ttk.Button(port_row, text="Scan", width=5, command=self.refresh_pump_ports)
        refresh_btn.pack(side=tk.LEFT)

        baud_row = ttk.Frame(conn_group)
        baud_row.pack(fill=tk.X, pady=4)
        ttk.Label(baud_row, text="Baudrate:").pack(side=tk.LEFT, padx=(0, 12))
        self.pump_baud_var = tk.StringVar(value="115200")
        self.pump_baud_combo = ttk.Combobox(
            baud_row, textvariable=self.pump_baud_var, values=["115200", "9600"], state="readonly", width=10
        )
        self.pump_baud_combo.pack(side=tk.LEFT)

        self.pump_connect_btn = ttk.Button(baud_row, text="Connect", command=self.toggle_pump_connection)
        self.pump_connect_btn.pack(side=tk.RIGHT)

        self.pump_status_label = ttk.Label(
            conn_group, text="Status: Disconnected", foreground="#dc2626", font=("Segoe UI", 9, "bold")
        )
        self.pump_status_label.pack(anchor="w", pady=(6, 0))

        # ---- Parameters Group ----
        param_group = ttk.LabelFrame(left_col, text=" Drop & Flow Calibration ", padding=10)
        param_group.pack(fill=tk.X, pady=(0, 10))

        vol_row = ttk.Frame(param_group)
        vol_row.pack(fill=tk.X, pady=3)
        ttk.Label(vol_row, text="Drop volume (µL):").pack(side=tk.LEFT)
        self.pump_vol_var = tk.StringVar(value="20.0")
        vol_entry = ttk.Entry(vol_row, textvariable=self.pump_vol_var, width=8, justify="center")
        vol_entry.pack(side=tk.RIGHT)
        vol_entry.bind("<KeyRelease>", lambda e: self.update_pump_metrics())

        pulse_row = ttk.Frame(param_group)
        pulse_row.pack(fill=tk.X, pady=3)
        ttk.Label(pulse_row, text="Pulse ON (ms):").pack(side=tk.LEFT)
        self.pump_pulse_var = tk.IntVar(value=self.default_pump_pulse)
        self.pump_pulse_scale = ttk.Scale(
            pulse_row, from_=5, to=80, variable=self.pump_pulse_var, orient=tk.HORIZONTAL,
            command=lambda v: self.on_pump_param_slider_change()
        )
        self.pump_pulse_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.pump_pulse_spin = ttk.Spinbox(
            pulse_row, from_=1, to=300, textvariable=self.pump_pulse_var, width=5, justify="center",
            command=self.update_pump_metrics
        )
        self.pump_pulse_spin.pack(side=tk.RIGHT)
        self.pump_pulse_spin.bind("<KeyRelease>", lambda e: self.update_pump_metrics())

        interval_row = ttk.Frame(param_group)
        interval_row.pack(fill=tk.X, pady=3)
        ttk.Label(interval_row, text="Interval OFF (ms):").pack(side=tk.LEFT)
        self.pump_interval_var = tk.IntVar(value=self.default_pump_interval)
        self.pump_interval_scale = ttk.Scale(
            interval_row, from_=20, to=800, variable=self.pump_interval_var, orient=tk.HORIZONTAL,
            command=lambda v: self.on_pump_param_slider_change()
        )
        self.pump_interval_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.pump_interval_spin = ttk.Spinbox(
            interval_row, from_=10, to=3000, textvariable=self.pump_interval_var, width=5, justify="center",
            command=self.update_pump_metrics
        )
        self.pump_interval_spin.pack(side=tk.RIGHT)
        self.pump_interval_spin.bind("<KeyRelease>", lambda e: self.update_pump_metrics())

        # Action buttons for timing
        btn_grid = ttk.Frame(param_group)
        btn_grid.pack(fill=tk.X, pady=(8, 2))

        r1 = ttk.Frame(btn_grid)
        r1.pack(fill=tk.X, pady=2)
        preset_btn = ttk.Button(r1, text="Preset 14 ms / 200 ms", command=self.apply_target_6ml_preset)
        preset_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        self.pump_apply_timing_btn = ttk.Button(r1, text="Apply to Pump", command=self.apply_pump_timing)
        self.pump_apply_timing_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(3, 0))

        r2 = ttk.Frame(btn_grid)
        r2.pack(fill=tk.X, pady=2)
        save_default_btn = ttk.Button(r2, text="⭐ Save as Default...", command=self.save_new_default_pump_timing)
        save_default_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        reset_factory_btn = ttk.Button(r2, text="Reset to Factory", command=self.reset_factory_pump_timing)
        reset_factory_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(3, 0))

        # ---- Workflow Automation ----
        auto_group = ttk.LabelFrame(left_col, text=" Measurement Coordination ", padding=10)
        auto_group.pack(fill=tk.X)
        auto_check = ttk.Checkbutton(
            auto_group,
            text="Auto-start pump on 'Start Measurement' and stop on finish",
            variable=self.auto_pump_on_measurement
        )
        auto_check.pack(anchor="w")

        tutorial_pump_btn = ttk.Button(
            auto_group,
            text="📖 Ver Tutorial del Flujo de Medición",
            command=self.show_measurement_tutorial
        )
        tutorial_pump_btn.pack(fill=tk.X, pady=(8, 0))

        # ---- Right column: Metrics Dashboard & Actions ----
        dash_group = ttk.LabelFrame(right_col, text=" Estimated Performance ", padding=10)
        dash_group.pack(fill=tk.X, pady=(0, 10))

        cards_frame = ttk.Frame(dash_group)
        cards_frame.pack(fill=tk.X, pady=4)

        c1 = ttk.LabelFrame(cards_frame, text=" Cadence ", padding=5)
        c1.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        self.metric_cadence_label = ttk.Label(c1, text="5.0 drops/s", font=("Segoe UI", 11, "bold"), anchor="center")
        self.metric_cadence_label.pack(pady=4)

        c2 = ttk.LabelFrame(cards_frame, text=" Flow Rate ", padding=5)
        c2.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        self.metric_flow_label = ttk.Label(
            c2, text="6.00 mL/min", font=("Segoe UI", 11, "bold"), anchor="center", foreground="#0284c7"
        )
        self.metric_flow_label.pack(pady=4)

        c3 = ttk.LabelFrame(cards_frame, text=" Period ", padding=5)
        c3.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=2)
        self.metric_period_label = ttk.Label(c3, text="200 ms", font=("Segoe UI", 11, "bold"), anchor="center")
        self.metric_period_label.pack(pady=4)

        actions_group = ttk.LabelFrame(right_col, text=" Manual Operation ", padding=10)
        actions_group.pack(fill=tk.X, pady=(0, 10))

        act_row = ttk.Frame(actions_group)
        act_row.pack(fill=tk.X, pady=4)

        self.single_drop_btn = ttk.Button(act_row, text="💧 1 Drop (Prime)", command=self.deliver_single_drop)
        self.single_drop_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        self.pump_start_btn = ttk.Button(act_row, text="▶ Start Pump", command=self.start_pump_flow)
        self.pump_start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        self.pump_stop_btn = ttk.Button(act_row, text="⏹ Stop Pump", command=self.stop_pump_flow, state=tk.DISABLED)
        self.pump_stop_btn.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(4, 0))

        log_group = ttk.LabelFrame(right_col, text=" Serial Activity Log ", padding=6)
        log_group.pack(fill=tk.BOTH, expand=True)

        self.pump_log_text = tk.Text(log_group, height=7, bg="#0f172a", fg="#38bdf8", font=("Consolas", 9), wrap=tk.WORD)
        log_scroll = ttk.Scrollbar(log_group, orient=tk.VERTICAL, command=self.pump_log_text.yview)
        self.pump_log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.pump_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.refresh_pump_ports()
        self.update_pump_metrics()

    def refresh_pump_ports(self):
        """Scan available serial ports and refresh combobox."""
        ports = list_serial_ports()
        self.pump_ports_list = ports
        display_values = [p[1] for p in ports]
        self.pump_port_combo['values'] = display_values
        if display_values:
            default_idx = 0
            for idx, p in enumerate(ports):
                if p[0] != "Simulation":
                    default_idx = idx
                    break
            self.pump_port_combo.current(default_idx)
        self._log_pump_message(f"Scanned {len(ports)} serial port options.")

    def _get_selected_pump_port(self):
        selected_desc = self.pump_port_var.get()
        for dev, desc in self.pump_ports_list:
            if desc == selected_desc:
                return dev
        return selected_desc or "COM3"

    def toggle_pump_connection(self):
        """Connect or disconnect the peristaltic pump."""
        if not self.pump.is_connected:
            port = self._get_selected_pump_port()
            try:
                baud = int(self.pump_baud_var.get())
            except ValueError:
                baud = 115200

            try:
                self.pump.connect(port=port, baudrate=baud)
                mode_str = "SIMULATION" if self.pump.is_simulation else f"{port} ({baud} baud)"
                self.pump_status_label.config(text=f"Status: Connected ({mode_str})", foreground="#16a34a")
                self.pump_connect_btn.config(text="Disconnect")
                self._log_pump_message(f"Connected successfully to {mode_str}.")
            except Exception as e:
                messagebox.showerror("Connection Error", f"Could not connect to {port}: {e}")
                self._log_pump_message(f"Connection failed: {e}")
        else:
            try:
                self.pump.disconnect()
            finally:
                self.pump_status_label.config(text="Status: Disconnected", foreground="#dc2626")
                self.pump_connect_btn.config(text="Connect")
                self.pump_start_btn.config(state=tk.NORMAL)
                self.pump_stop_btn.config(state=tk.DISABLED)
                self._log_pump_message("Disconnected.")

    def on_pump_param_slider_change(self):
        self.update_pump_metrics()

    def update_pump_metrics(self):
        """Recalculate cadence, flow rate and period."""
        try:
            pulse = self.pump_pulse_var.get()
            interval = self.pump_interval_var.get()
            vol = float(self.pump_vol_var.get())
        except (ValueError, tk.TclError):
            return

        metrics = self.pump.calculate_metrics(pulse_ms=pulse, interval_ms=interval, drop_volume_ul=vol)
        self.metric_cadence_label.config(text=f"{metrics['drops_per_second']:.1f} drops/s")
        self.metric_flow_label.config(text=f"{metrics['flow_rate_ml_min']:.2f} mL/min")
        self.metric_period_label.config(text=f"{int(metrics['cycle_time_ms'])} ms")

    def apply_target_6ml_preset(self):
        """Configure hardware calibrated default (14 ms pulse + 200 ms interval)."""
        pulse = 14
        interval = 200
        self.pump_pulse_var.set(pulse)
        self.pump_interval_var.set(interval)
        self.update_pump_metrics()
        self._log_pump_message("Preset applied: pulse=14 ms, interval=200 ms (entregarGota(14) + delay(200)).")
        if self.pump.is_connected:
            self.apply_pump_timing()

    # ---- Persistence helpers for pump timing defaults ----
    def load_pump_timing_default(self) -> tuple[int, int]:
        """Return saved default (pulse_ms, interval_ms) or factory default (14, 200)."""
        try:
            with open(get_pump_timing_file(), "r", encoding="utf-8") as f:
                content = f.read().strip()
                if "," in content:
                    parts = content.split(",")
                else:
                    parts = content.split()
                if len(parts) >= 2:
                    p = int(parts[0])
                    i = int(parts[1])
                    if p > 0 and i > 0:
                        return p, i
        except Exception:
            pass
        return 14, 200

    def save_pump_timing_default(self, pulse: int, interval: int) -> None:
        """Persist default pump timing to user state folder."""
        with open(get_pump_timing_file(), "w", encoding="utf-8") as f:
            f.write(f"{int(pulse)},{int(interval)}\n")

    def save_new_default_pump_timing(self):
        """Prompt confirmation and save current parameters as the new permanent default."""
        try:
            pulse = int(self.pump_pulse_var.get())
            interval = int(self.pump_interval_var.get())
            if pulse <= 0 or interval <= 0:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("Valores inválidos", "El pulso y el intervalo deben ser números enteros positivos.")
            return

        confirm = messagebox.askyesno(
            "Confirmar Nuevo Valor por Defecto",
            f"¿Estás seguro de que deseas guardar esta configuración como el nuevo valor POR DEFECTO?\n\n"
            f"• Pulso ON: {pulse} ms\n"
            f"• Intervalo OFF: {interval} ms\n\n"
            "Estos valores se cargarán automáticamente cada vez que inicies el programa.",
            icon="warning"
        )
        if confirm:
            self.save_pump_timing_default(pulse, interval)
            self._log_pump_message(f"Nuevo valor por defecto guardado: Pulso={pulse} ms, Intervalo={interval} ms.")
            messagebox.showinfo("Configuración Guardada", f"Nuevo valor por defecto establecido:\nPulso: {pulse} ms\nIntervalo: {interval} ms")

    def reset_factory_pump_timing(self):
        """Reset default parameters back to factory values (14 ms / 200 ms)."""
        confirm = messagebox.askyesno(
            "Restablecer Valores de Fábrica",
            "¿Deseas restablecer los valores por defecto a los de fábrica (Pulso: 14 ms, Intervalo: 200 ms)?",
            icon="question"
        )
        if confirm:
            self.save_pump_timing_default(14, 200)
            self.pump_pulse_var.set(14)
            self.pump_interval_var.set(200)
            self.update_pump_metrics()
            self._log_pump_message("Valores por defecto restablecidos a fábrica (14 ms / 200 ms).")
            if self.pump.is_connected:
                self.apply_pump_timing()
            messagebox.showinfo("Restablecido", "Valores restablecidos a fábrica: 14 ms pulso, 200 ms intervalo.")

    def apply_pump_timing(self):
        """Send pulse and interval timings to the connected microcontroller."""
        if not self.pump.is_connected:
            self._log_pump_message("Cannot apply timing: Pump is not connected.")
            messagebox.showwarning("Not Connected", "Please connect to the pump controller first.")
            return

        pulse = self.pump_pulse_var.get()
        interval = self.pump_interval_var.get()
        try:
            resp = self.pump.set_timing(pulse, interval)
            self._log_pump_message(f"Sent: SET {pulse} {interval} -> {resp}")
        except Exception as e:
            self._log_pump_message(f"Error applying timing: {e}")

    def deliver_single_drop(self):
        """Deliver one test drop."""
        if not self.pump.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to the pump controller first.")
            return

        try:
            resp = self.pump.single_drop()
            self._log_pump_message(f"Single drop pulse triggered -> {resp}")
        except Exception as e:
            self._log_pump_message(f"Error delivering drop: {e}")

    def start_pump_flow(self):
        """Start continuous flow."""
        if not self.pump.is_connected:
            messagebox.showwarning("Not Connected", "Please connect to the pump controller first.")
            return

        try:
            resp = self.pump.start()
            self.pump_start_btn.config(state=tk.DISABLED)
            self.pump_stop_btn.config(state=tk.NORMAL)
            self.pump_status_label.config(
                text=f"Status: RUNNING ({self.pump.port})", foreground="#0284c7"
            )
            self._log_pump_message(f"Pump continuous flow started -> {resp}")
        except Exception as e:
            self._log_pump_message(f"Error starting pump: {e}")
            messagebox.showerror("Error", f"Failed to start pump: {e}")

    def stop_pump_flow(self):
        """Stop continuous flow."""
        if not self.pump.is_connected:
            return

        try:
            resp = self.pump.stop()
            self.pump_start_btn.config(state=tk.NORMAL)
            self.pump_stop_btn.config(state=tk.DISABLED)
            mode_str = "SIMULATION" if self.pump.is_simulation else self.pump.port
            self.pump_status_label.config(
                text=f"Status: Connected ({mode_str})", foreground="#16a34a"
            )
            self._log_pump_message(f"Pump stopped -> {resp}")
        except Exception as e:
            self._log_pump_message(f"Error stopping pump: {e}")

    def _log_pump_message(self, message: str):
        """Append timestamped message to the pump log box."""
        if hasattr(self, 'pump_log_text') and self.pump_log_text:
            timestamp = time.strftime("%H:%M:%S")
            self.pump_log_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.pump_log_text.see(tk.END)

    def show_measurement_tutorial(self):
        """Display an interactive, guided step-by-step measurement tutorial."""
        tut_win = tk.Toplevel(self.root)
        tut_win.title("Tutorial: Flujo de Medición con Bomba Peristáltica")
        tut_win.geometry("700x580")
        tut_win.minsize(580, 480)

        # Header Frame
        header = tk.Frame(tut_win, bg="#0f172a", padx=16, pady=14)
        header.pack(fill=tk.X)

        title = tk.Label(
            header,
            text="Guía Paso a Paso: Ensayo con Bomba Peristáltica",
            font=("Segoe UI", 13, "bold"),
            fg="#f8fafc",
            bg="#0f172a",
        )
        title.pack(anchor="w")

        subtitle = tk.Label(
            header,
            text="Sigue estos pasos para realizar una adquisición automatizada sin tocar válvulas manuales.",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#0f172a",
        )
        subtitle.pack(anchor="w", pady=(2, 0))

        # Scrollable container for steps
        canvas = tk.Canvas(tut_win, bg="#f8fafc", highlightthickness=0)
        scrollbar = ttk.Scrollbar(tut_win, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollable_frame = tk.Frame(canvas, bg="#f8fafc", padx=16, pady=12)
        window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _on_frame_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(e):
            canvas.itemconfig(window_id, width=e.width)

        scrollable_frame.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        steps = [
            (
                "Paso 1: Preparación física y encuadre",
                "Pestaña 'Camera'",
                [
                    "Coloca el agregado de suelo seco centrado en el soporte bajo la aguja hipodérmica.",
                    "En la pestaña 'Camera', presiona 'Start Preview' para verificar que la muestra esté nítida y bien iluminada.",
                    "Presiona 'Stop Preview' antes de continuar para liberar el dispositivo de cámara.",
                ],
                "#0284c7"
            ),
            (
                "Paso 2: Conexión y cebado de la bomba",
                "Pestaña 'Pump Control'",
                [
                    "Selecciona el puerto COM de tu Arduino/ESP32 y presiona 'Connect' (aparecerá en verde).",
                    "Verifica los tiempos: 14 ms de pulso y 200 ms de intervalo (calibrado a 6.0 mL/min).",
                    "Presiona '💧 1 Drop (Prime)' dos o tres veces para purgar burbujas de aire en la manguera y cebar la aguja.",
                    "Confirma que la opción 'Auto-start pump on Start Measurement' esté marcada.",
                ],
                "#16a34a"
            ),
            (
                "Paso 3: Verificación del umbral del fotodiodo",
                "Pestaña 'Set Threshold'",
                [
                    "Asegúrate de haber calibrado previamente el umbral del fotodiodo.",
                    "Si es la primera vez en la sesión, recolecta unas medidas, haz clic sobre el gráfico para situar la línea roja entre el nivel de reposo y la caída de luz de la gota, y confirma.",
                ],
                "#d97706"
            ),
            (
                "Paso 4: Adquisición automatizada",
                "Pestaña 'Measurement'",
                [
                    "Selecciona el dispositivo de cámara y tu DAC (ArduinoUno o NIUSB6009).",
                    "Indica el número de gotas a registrar (ej. 100) y los fotogramas previos.",
                    "Presiona 'Save File As' y elige la ruta donde guardar el archivo de video (.avi).",
                    "Haz clic en 'Start Measurement':",
                    "  ▶ La bomba peristáltica arrancará de forma automática y continua.",
                    "  ▶ Cada gota será detectada por el fotodiodo y la cámara capturará el impacto.",
                    "  ▶ El contador avanzará en tiempo real en la pantalla.",
                    "  ⏹ Al alcanzar el total de gotas (o si presionas 'Stop Measurement'), la bomba se apagará sola y el video se guardará en disco.",
                ],
                "#4f46e5"
            ),
            (
                "Paso 5: Análisis posterior",
                "Pestañas 'Drop Energy' y 'Video Processing'",
                [
                    "En 'Drop Energy', calcula la velocidad final y la energía de impacto de la gota.",
                    "En 'Video Processing', carga la carpeta de videos grabados para procesar la desintegración del agregado y determinar el número de gotas de ruptura.",
                ],
                "#64748b"
            ),
        ]

        for num, (title_text, tab_badge, items, color) in enumerate(steps, start=1):
            card = tk.Frame(scrollable_frame, bg="#ffffff", bd=1, relief=tk.SOLID, padx=12, pady=10)
            card.pack(fill=tk.X, pady=(0, 10))

            top_row = tk.Frame(card, bg="#ffffff")
            top_row.pack(fill=tk.X, pady=(0, 4))

            num_lbl = tk.Label(
                top_row,
                text=f"{num}",
                font=("Segoe UI", 10, "bold"),
                fg="#ffffff",
                bg=color,
                width=2,
                padx=4,
                pady=1
            )
            num_lbl.pack(side=tk.LEFT, padx=(0, 8))

            t_lbl = tk.Label(
                top_row,
                text=title_text,
                font=("Segoe UI", 10, "bold"),
                fg="#0f172a",
                bg="#ffffff"
            )
            t_lbl.pack(side=tk.LEFT)

            badge_lbl = tk.Label(
                top_row,
                text=tab_badge,
                font=("Segoe UI", 8, "bold"),
                fg=color,
                bg="#f1f5f9",
                padx=6,
                pady=2
            )
            badge_lbl.pack(side=tk.RIGHT)

            for it in items:
                it_lbl = tk.Label(
                    card,
                    text=f"• {it}" if not it.startswith("  ") else it,
                    font=("Segoe UI", 9),
                    fg="#334155",
                    bg="#ffffff",
                    wraplength=600,
                    justify=tk.LEFT,
                    anchor="w"
                )
                it_lbl.pack(fill=tk.X, pady=1, padx=(26, 0))

        # Bottom footer button
        bottom_bar = tk.Frame(tut_win, bg="#f1f5f9", padx=16, pady=10)
        bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)

        close_btn = ttk.Button(bottom_bar, text="¡Entendido! Cerrar", command=tut_win.destroy)
        close_btn.pack(side=tk.RIGHT)

    # Setup the 30-Aggregate Carousel & Laser Reader tab
    def setup_carousel_tab(self):
        container = ttk.Frame(self.carousel_frame, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        left_col = ttk.Frame(container)
        left_col.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        right_col = ttk.Frame(container)
        right_col.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # ---- Connection & Motor Configuration ----
        conn_group = ttk.LabelFrame(left_col, text=" ESP32 / Stepper 28BYJ-48 (ULN2003) & Laser Reader ", padding=8)
        conn_group.pack(fill=tk.X, pady=(0, 8))

        share_check = ttk.Checkbutton(
            conn_group,
            text="Share serial port with Peristaltic Pump (Single ESP32/Arduino)",
            variable=self.share_pump_serial_var
        )
        share_check.pack(anchor="w", pady=(0, 4))

        port_row = ttk.Frame(conn_group)
        port_row.pack(fill=tk.X, pady=3)
        ttk.Label(port_row, text="Carousel Port:").pack(side=tk.LEFT, padx=(0, 6))
        self.carousel_port_var = tk.StringVar(value="Simulation")
        self.carousel_port_combo = ttk.Combobox(port_row, textvariable=self.carousel_port_var, state="readonly", width=22)
        self.carousel_port_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.carousel_connect_btn = ttk.Button(port_row, text="Connect", command=self.toggle_carousel_connection)
        self.carousel_connect_btn.pack(side=tk.RIGHT)

        motor_row = ttk.Frame(conn_group)
        motor_row.pack(fill=tk.X, pady=3)
        ttk.Label(motor_row, text="Drive Mode:").pack(side=tk.LEFT)
        self.carousel_motor_var = tk.StringVar(value="STEPPER_28BYJ48")
        ttk.Combobox(
            motor_row,
            textvariable=self.carousel_motor_var,
            values=["STEPPER_28BYJ48", "DC_HBRIDGE"],
            state="readonly",
            width=18
        ).pack(side=tk.RIGHT)

        steps_row = ttk.Frame(conn_group)
        steps_row.pack(fill=tk.X, pady=3)
        ttk.Label(steps_row, text="Steps per Slot (12°):").pack(side=tk.LEFT)
        self.carousel_steps_var = tk.IntVar(value=self.default_carousel_steps)
        ttk.Spinbox(steps_row, from_=10, to=2000, textvariable=self.carousel_steps_var, width=7, justify="center").pack(side=tk.RIGHT)

        laser_row = ttk.Frame(conn_group)
        laser_row.pack(fill=tk.X, pady=2)
        self.carousel_use_laser_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            laser_row,
            text="Stop & align on Optical Laser Reader (Sub-mm precision)",
            variable=self.carousel_use_laser_var
        ).pack(anchor="w")

        cfg_btns = ttk.Frame(conn_group)
        cfg_btns.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(cfg_btns, text="Apply Config", command=self.apply_carousel_config).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        ttk.Button(cfg_btns, text="⭐ Save Default", command=self.save_new_default_carousel_config).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(3, 0))

        self.carousel_status_label = ttk.Label(
            conn_group, text="Status: Ready (Simulation / Shared)", foreground="#16a34a", font=("Segoe UI", 9, "bold")
        )
        self.carousel_status_label.pack(anchor="w", pady=(4, 0))

        # ---- Positioning & Laser Alignment Controls ----
        pos_group = ttk.LabelFrame(left_col, text=" Positioning & Laser Alignment ", padding=8)
        pos_group.pack(fill=tk.X, pady=(0, 8))

        status_row = ttk.Frame(pos_group)
        status_row.pack(fill=tk.X, pady=4)
        self.carousel_slot_badge = ttk.Label(
            status_row, text="SLOT 1 / 30", font=("Segoe UI", 13, "bold"), foreground="#0284c7"
        )
        self.carousel_slot_badge.pack(side=tk.LEFT)
        self.carousel_laser_badge = ttk.Label(
            status_row, text="🟢 LASER: ALIGNED", font=("Segoe UI", 10, "bold"), foreground="#16a34a"
        )
        self.carousel_laser_badge.pack(side=tk.RIGHT)

        nav_row = ttk.Frame(pos_group)
        nav_row.pack(fill=tk.X, pady=4)
        ttk.Button(nav_row, text="⏮ Home (#1)", command=self.carousel_home).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(nav_row, text="◀ Prev", command=self.carousel_prev).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(nav_row, text="Next ▶", command=self.carousel_next).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        goto_row = ttk.Frame(pos_group)
        goto_row.pack(fill=tk.X, pady=4)
        ttk.Label(goto_row, text="Target Slot (1-30):").pack(side=tk.LEFT)
        self.carousel_goto_var = tk.IntVar(value=1)
        ttk.Spinbox(goto_row, from_=1, to=30, textvariable=self.carousel_goto_var, width=5, justify="center").pack(side=tk.LEFT, padx=6)
        ttk.Button(goto_row, text="Go to Slot", command=self.carousel_goto).pack(side=tk.LEFT, padx=2)
        ttk.Button(goto_row, text="-5 Steps", width=8, command=lambda: self.carousel_jog(-5)).pack(side=tk.RIGHT, padx=2)
        ttk.Button(goto_row, text="+5 Steps", width=8, command=lambda: self.carousel_jog(5)).pack(side=tk.RIGHT, padx=2)

        # ---- Mechanical & Anti-Splash Specs ----
        geom = CarouselController.calculate_geometry(total_slots=30, min_arc_spacing_cm=3.5)
        spec_group = ttk.LabelFrame(left_col, text=" Carousel Mechanical Design ", padding=8)
        spec_group.pack(fill=tk.BOTH, expand=True)
        spec_text = (
            f"• Disc Diameter: {geom['disc_diameter_cm']} cm (Radius {geom['disc_radius_cm']} cm)\n"
            f"• Support Spacing: {geom['arc_spacing_cm']} cm (> 3.0 cm splash zone + radial baffles)\n"
            f"• Angular Step: {geom['angle_per_slot_deg']}° per sample ({geom['steps_per_slot']} half-steps)\n"
            f"• Linear Resolution: {geom['positioning_resolution_mm']} mm/step + Laser Index Stop\n"
            f"• Support Orifice: Ø {geom['support_hole_diameter_mm']} mm (Area {geom['support_hole_area_mm2']} mm²)"
        )
        ttk.Label(spec_group, text=spec_text, justify=tk.LEFT, font=("Segoe UI", 9)).pack(anchor="w")

        # ---- Right Column: 30-Aggregate Status Matrix ----
        grid_group = ttk.LabelFrame(right_col, text=" 30-Aggregate Measurement Matrix (Real-Time Status) ", padding=8)
        grid_group.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        matrix_frame = ttk.Frame(grid_group)
        matrix_frame.pack(fill=tk.BOTH, expand=True)

        self.slot_cell_labels = {}
        for s in range(1, 31):
            r = (s - 1) // 5
            c = (s - 1) % 5
            cell = tk.Label(
                matrix_frame,
                text=f"#{s:02d}\nPENDING",
                bg="#f1f5f9",
                fg="#334155",
                font=("Segoe UI", 8, "bold"),
                relief=tk.RIDGE,
                bd=1,
                padx=4,
                pady=6,
                width=10
            )
            cell.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
            self.slot_cell_labels[s] = cell

        for r in range(6):
            matrix_frame.rowconfigure(r, weight=1)
        for c in range(5):
            matrix_frame.columnconfigure(c, weight=1)

        matrix_btns = ttk.Frame(right_col)
        matrix_btns.pack(fill=tk.X)
        ttk.Button(matrix_btns, text="🔄 Reset 30 Slots", command=self.reset_carousel_matrix).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))
        ttk.Button(matrix_btns, text="💾 Export 30-Sample CSV", command=self.export_carousel_results_dialog).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(4, 0))

        # Populate ports and connect in Simulation by default so carousel is ready out-of-the-box
        ports = list_serial_ports()
        self.carousel_port_combo["values"] = [p[1] for p in ports]
        if ports:
            self.carousel_port_combo.current(len(ports) - 1)  # Default to Simulation
        self.carousel.connect(port="Simulation")
        self.update_carousel_slot_grid()

    def load_carousel_config_default(self) -> tuple[int, int]:
        """Return saved (total_slots, steps_per_slot) or factory default (30, 137)."""
        try:
            with open(get_carousel_config_file(), "r", encoding="utf-8") as f:
                parts = f.read().strip().replace(",", " ").split()
                if len(parts) >= 2:
                    s = int(parts[0])
                    st = int(parts[1])
                    if s > 0 and st > 0:
                        return s, st
        except Exception:
            pass
        return 30, 137

    def save_carousel_config_default(self, total_slots: int, steps_per_slot: int) -> None:
        with open(get_carousel_config_file(), "w", encoding="utf-8") as f:
            f.write(f"{int(total_slots)},{int(steps_per_slot)}\n")

    def save_new_default_carousel_config(self):
        try:
            steps = int(self.carousel_steps_var.get())
            if steps <= 0:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("Invalid Value", "Steps per slot must be a positive integer.")
            return
        self.save_carousel_config_default(30, steps)
        messagebox.showinfo("Saved", f"Saved default carousel configuration: 30 slots, {steps} steps/slot.")

    def toggle_carousel_connection(self):
        if self.share_pump_serial_var.get() and self.pump.is_connected:
            self.carousel.connect(shared_pump=self.pump)
            self.carousel_status_label.config(text=f"Status: Shared with Pump ({self.pump.port})", foreground="#16a34a")
            return

        selected_desc = self.carousel_port_var.get()
        port = "Simulation"
        for dev, desc in getattr(self, "pump_ports_list", []):
            if desc == selected_desc:
                port = dev
                break
        try:
            self.carousel.disconnect()
            self.carousel.connect(port=port)
            mode = "SIMULATION" if self.carousel.is_simulation else port
            self.carousel_status_label.config(text=f"Status: Connected ({mode})", foreground="#16a34a")
        except Exception as e:
            messagebox.showerror("Carousel Error", f"Could not connect carousel on {port}: {e}")

    def apply_carousel_config(self):
        try:
            steps = int(self.carousel_steps_var.get())
            mode = self.carousel_motor_var.get()
            self.carousel.use_laser_stop = bool(self.carousel_use_laser_var.get())
            self.carousel.configure(total_slots=30, steps_per_slot=steps, motor_mode=mode)
            self._log_pump_message(f"Carousel config updated: 30 slots, {steps} steps/slot, mode={mode}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not apply carousel config: {e}")

    def _ensure_carousel_ready(self):
        if self.share_pump_serial_var.get() and self.pump.is_connected:
            self.carousel.shared_pump = self.pump
        elif not self.carousel.is_connected:
            self.carousel.connect(port="Simulation")

    def _sync_carousel_badges(self):
        slot = self.carousel.current_slot
        total = self.carousel.total_slots
        laser_ok = self.carousel.laser_aligned
        laser_txt = "ALIGNED" if laser_ok else "SEARCHING"
        if hasattr(self, "carousel_slot_badge"):
            self.carousel_slot_badge.config(text=f"SLOT {slot} / {total}")
        if hasattr(self, "carousel_laser_badge"):
            self.carousel_laser_badge.config(
                text=f"🟢 LASER: {laser_txt}" if laser_ok else f"🟡 LASER: {laser_txt}",
                foreground="#16a34a" if laser_ok else "#d97706"
            )
        if hasattr(self, "realtime_slot_label"):
            self.realtime_slot_label.config(text=f"Carousel Slot: {slot} / {total} | Laser Reader: {laser_txt}")
        self.update_carousel_slot_grid()

    def carousel_next(self):
        self._ensure_carousel_ready()
        res = self.carousel.next_slot()
        self._sync_carousel_badges()
        self._log_pump_message(f"Carousel advanced -> Slot {res['slot']} (Laser={res['laser_aligned']})")

    def carousel_prev(self):
        self._ensure_carousel_ready()
        res = self.carousel.prev_slot()
        self._sync_carousel_badges()
        self._log_pump_message(f"Carousel reversed -> Slot {res['slot']} (Laser={res['laser_aligned']})")

    def carousel_home(self):
        self._ensure_carousel_ready()
        res = self.carousel.home()
        self._sync_carousel_badges()
        self._log_pump_message(f"Carousel homed -> Slot {res['slot']} (Laser={res['laser_aligned']})")

    def carousel_goto(self):
        self._ensure_carousel_ready()
        target = self.carousel_goto_var.get()
        res = self.carousel.goto_slot(target)
        self._sync_carousel_badges()
        self._log_pump_message(f"Carousel moved to Slot {res['slot']} (Laser={res['laser_aligned']})")

    def carousel_jog(self, steps: int):
        self._ensure_carousel_ready()
        resp = self.carousel.fine_step(steps)
        self._log_pump_message(f"Carousel fine step ({steps}) -> {resp}")

    def reset_carousel_matrix(self):
        self.carousel.reset_slot_results()
        self.update_carousel_slot_grid()

    def update_carousel_slot_grid(self):
        if not hasattr(self, "slot_cell_labels"):
            return
        cur = self.carousel.current_slot
        for s, lbl in self.slot_cell_labels.items():
            info = self.carousel.slot_results.get(s, {})
            st = info.get("status", "PENDING")
            drops = info.get("drops", 0)
            nrg = info.get("energy_mj", 0.0)
            if st == "BROKEN":
                bg = "#dcfce7"
                fg = "#166534"
                txt = f"#{s:02d} BROKEN\n{drops} d ({nrg:.1f}mJ)"
            elif st == "STABLE":
                bg = "#dbeafe"
                fg = "#1e40af"
                txt = f"#{s:02d} STABLE\n{drops} d ({nrg:.1f}mJ)"
            elif st == "MEASURING":
                bg = "#fef9c3"
                fg = "#854d0e"
                txt = f"#{s:02d} ACTIVE\nMeasuring..."
            else:
                bg = "#e0f2fe" if s == cur else "#f1f5f9"
                fg = "#0369a1" if s == cur else "#475569"
                txt = f"#{s:02d} {'[READY]' if s == cur else 'PENDING'}"
            lbl.config(text=txt, bg=bg, fg=fg)

    def export_carousel_results_dialog(self):
        path = fd.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")],
            title="Export 30-Aggregate Carousel Results"
        )
        if path:
            self.export_carousel_results_csv(path)
            messagebox.showinfo("Export Complete", f"Saved 30-aggregate results to:\n{path}")

    def export_carousel_results_csv(self, csv_path: str) -> str:
        import csv
        rows = []
        energies = []
        for s in range(1, self.carousel.total_slots + 1):
            info = self.carousel.slot_results[s]
            rows.append([
                info["slot"],
                info["status"],
                info["drops"],
                info["energy_mj"],
                info["initial_area_px"],
                info["final_area_px"],
                info["normalized_final"],
                info["video_file"],
            ])
            if info["status"] in ("BROKEN", "STABLE") and info["drops"] > 0:
                energies.append(float(info["energy_mj"]))

        median_energy = round(statistics.median(energies), 4) if energies else 0.0
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Slot", "Status", "Rupture_Drops", "Breakdown_Energy_mJ",
                "Initial_Area_px2", "Final_Area_px2", "Final_Normalized_Area", "Video_File"
            ])
            writer.writerows(rows)
            writer.writerow([])
            writer.writerow(["Median_Breakdown_Energy_mJ", median_energy])
        return csv_path

    def on_app_close(self):
        """Clean shutdown when closing the main window."""
        try:
            self.cleanup_camera()
        except Exception:
            pass
        try:
            self.cleanup_dac()
        except Exception:
            pass
        if hasattr(self, 'carousel') and self.carousel:
            try:
                self.carousel.disconnect()
            except Exception:
                pass
        if hasattr(self, 'pump') and self.pump:
            try:
                self.pump.disconnect()
            except Exception:
                pass
        self.root.destroy()

#ENDS THE TABS DEFINITIONS

#Functions for the camera tab
    def start_preview(self, *args):
        """Start the camera preview."""
        # Close any existing resources
        self.cleanup_camera()
        
        self.cleanup_dac()
        

        
        # Get selected device
        selected_device = int(self.device_var.get())
        
        # Initialize camera if not already done
        if not hasattr(self, 'camera') or not self.camera:
            self.camera = cam(fps=1, width=640, height=480)
            self.camera.start(device=selected_device)
        
        # Set flag to continue preview
        self.conti = True
        
        # Start the non-blocking update loop
        self.update_camera_preview()
    
    def stop_preview(self, *args):
        """Stop the camera preview."""
        # Set flag to stop the preview loop
        self.conti = False
        
        # Stop and close the camera if needed
        if hasattr(self, 'camera') and self.camera:
            self.camera.stop()
            self.camera.close_window()
            self.camera = None
            
        # Clear the preview image
        self.preview_label.configure(image='')

    def update_camera_preview(self):
        """Update the camera preview in a non-blocking way."""
        if hasattr(self, 'conti') and self.conti and hasattr(self, 'camera'):
            # Get frame from camera
            img, wait_key = self.camera.preview_camera()
            
            # Convert numpy array to PIL Image
            pil_img = Image.fromarray(img)
            
            # Convert PIL Image to Tkinter PhotoImage
            tk_img = ImageTk.PhotoImage(image=pil_img)
            
            # Update the label with the new image
            self.preview_label.configure(image=tk_img)
            self.preview_label.image = tk_img  # Keep a reference to prevent garbage collection
            
            # Schedule the next update
            self.root.after(30, self.update_camera_preview)  # ~33 FPS

 #Functions of the threshold tab   
    def set_threshold(self, *args):
        """Start the measurement and display the plot for threshold selection."""
        # Close any existing resources
        self.cleanup_camera()

        # Get the number of measures from the input field
        try:
            measures = int(self.measures_var.get())
            if measures <= 0:
                raise ValueError("Number of measures must be positive.")
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid positive number for measures.")
            return

        selected_dac = self.DAC_var_threshold.get()

        def _acquisition_worker():
            values = None
            error_msg = None

            try:
                # Set procedure according to the selected DAC
                if selected_dac == "NIUSB6009":
                    measurer = NIUSB6009(device_name="Dev1", channel="ai0", sample_rate=1000, samples_per_channel=10000)
                    measurer.start()
                    
                    i = 0
                    temp_values = []
                    while i < measures:
                        value = measurer.measure()
                        temp_values.append([i, value])
                        i += 1

                    values = np.array(temp_values)
                    measurer.stop()
                    measurer.close()

                elif selected_dac == "ArduinoUno":
                    measurer = ArduinoUno(port="COM3", baudrate=115200)  # Ajustar puerto según corresponda
                    measurer.start()
                    
                    i = 0
                    temp_values = []
                    while i < measures:
                        value = measurer.measure()
                        if value is not None:  # Ignorar lecturas fallidas por timeout o buffer vacío
                            temp_values.append([i, value])
                            i += 1

                    values = np.array(temp_values)
                    measurer.stop()
                    measurer.close()

                elif selected_dac == "Test":
                    file_path = os.path.join(os.path.dirname(__file__), "for_test.tsv")
                    with open(file_path) as f:
                        lines = f.readlines()
                        values = np.array([list(map(float, line.split())) for line in lines])[:measures]

            except Exception as e:
                error_msg = str(e)

            # Retornar los datos al hilo principal de Tkinter para graficar
            self.root.after(0, lambda: self._on_set_threshold_finished(values, error_msg))

        # Iniciar la captura de datos en segundo plano sin congelar Tkinter
        threading.Thread(target=_acquisition_worker, daemon=True).start()


    def _on_set_threshold_finished(self, values, error_msg):
        """Callback ejecutado en el hilo principal tras obtener los datos."""
        if error_msg:
            messagebox.showerror("Error", f"An error occurred while measuring: {error_msg}")
            return

        if values is None or len(values) == 0:
            return

        # Store the values for later use
        self.measurement_values = values
        
        # Clear any existing plot
        for widget in self.threshold_plot_frame.winfo_children():
            widget.destroy()
        
        # Create a new matplotlib figure
        self.fig = Figure(figsize=(6, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        
        # Plot the data
        self.ax.plot(values[:, 0], values[:, 1])
        self.ax.set_title("Click to set threshold level")
        
        # Create a canvas to display the figure in Tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.threshold_plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Connect the click event
        self.canvas.mpl_connect('button_press_event', self.on_plot_click)
        
        # Disable the confirm button initially
        self.threshold_confirm_button.config(state=tk.DISABLED)
    
    def on_plot_click(self, event):
        """Handle click events on the plot."""
        if event.ydata is not None:
            # Store the threshold value
            self.threshold_value = event.ydata
            
            # Clear the previous plot
            self.ax.clear()
            
            # Redraw the data
            self.ax.plot(self.measurement_values[:, 0], self.measurement_values[:, 1])
            
            # Draw the threshold line
            self.ax.axhline(y=self.threshold_value, color='r', linestyle='-')
            self.ax.set_title(f"Threshold set at y = {self.threshold_value:.4f}")
            
            # Update the canvas
            self.canvas.draw()
            
            # Enable the confirm button
            self.threshold_confirm_button.config(state=tk.NORMAL)
    
    def confirm_threshold(self):
        """Confirm the selected threshold."""
        if self.threshold_value is not None:
            messagebox.showinfo("Threshold Confirmed", f"Threshold value {self.threshold_value:.4f} has been set.")
            
            # Disable the threshold confirm button
            self.threshold_confirm_button.config(state=tk.DISABLED)
            
            threshold_file = get_threshold_file()
            with open(threshold_file, "w", encoding="utf-8") as f:
                f.write(f"{self.threshold_value}\n")

#Functions of the measurement tab    
    def save_file_as(self):
        self.nombrevid = fd.asksaveasfilename(defaultextension = 'avi',filetypes=[('Avi Files', '*.avi'), ('All Files', '*.*')])
        if self.nombrevid:
            self.start_measurement_button.config(state=tk.NORMAL)
            self.measured_drops_label.config(text='Number of drops registered: ' + str(0))

    def cleanup_camera(self):
        if hasattr(self, 'camera') and self.camera:
            try:
                self.camera.stop()
                self.camera.close_window()
            except Exception:
                pass
            self.camera = None

    def cleanup_dac(self):
        if hasattr(self, 'measurer') and self.measurer:
            try:
                self.measurer.stop()
                self.measurer.close()
            except Exception:
                pass
            self.measurer = None            

    def start_measurement(self):
        """Start the measurement process."""
        # Close any existing resources
        self.cleanup_camera()
        
        self.cleanup_dac()
        
        # Stop and close the camera if needed
        if hasattr(self, 'camera') and self.camera:
            self.cleanup_camera()

        # Get the number of drops from the input field
        try:
            self.total_drops = int(self.measures_drops.get())
            if self.total_drops <= 0:
                raise ValueError("Number of drops must be positive.")
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid positive number for drops.")
            return

        # Get the number of previous frames from the input field
        try:
            frames = int(self.measures_frames.get())
            if frames <= 0:
                raise ValueError("Number of previous frames must be positive.")
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid positive number for previous frames.")
            return
        
        # Load the threshold value from the state file
        try:
            with open(get_threshold_file(), "r", encoding="utf-8") as f:
                self.threshold = float(f.readline())
        except FileNotFoundError:
            messagebox.showerror("Error", "Threshold file not found. Please set the threshold first.")
            return

        # Disable the start button to prevent multiple clicks
        self.start_measurement_button.config(state=tk.DISABLED)
        # Enable the stop button
        self.stop_measurement_button.config(state=tk.NORMAL)

        # The selected device is stored for all the measurement session
        self.selected_dac = self.DAC_var_measure.get()

        # Get selected device
        selected_device = int(self.device_var_measure.get())
        
        # Initialize camera if not already done
        if not hasattr(self, 'camera') or not self.camera:
            self.camera = cam(fps=1, width=640, height=480)
            self.camera.start(device=selected_device)

        # Initialize list in RAM memory
        self.captured_frames = []

        self.camera.path_name_save_video = self.nombrevid
        self.camera.set_path_name_save_video()

        # Configure Real-Time Wear Analyzer & Carousel Batch
        try:
            hole_area_val = float(self.realtime_hole_area_var.get())
            if hole_area_val <= 0:
                hole_area_val = 4000.0
        except Exception:
            hole_area_val = 4000.0
        self.wear_analyzer.hole_area_px = hole_area_val
        self.wear_analyzer.reset()
        self.latest_wear_info = None
        self.sample_broken_in_realtime = False
        self.user_stopped_measurement = False

        try:
            self.batch_target_count = max(1, min(30, int(self.batch_samples_var.get())))
        except Exception:
            self.batch_target_count = 1
        if not self.auto_carousel_on_rupture.get():
            self.batch_target_count = 1
        self.batch_measured_count = 0

        self._ensure_carousel_ready()
        self.carousel.slot_results[self.carousel.current_slot]["status"] = "MEASURING"
        self._sync_carousel_badges()

        # Initialize drop counter
        self.current_drops = 0
        self.measuring = True
        
        # Write initial frames to the video file
        self.frame_count = 0
        self.total_frames = frames
        self.write_initial_frames()
    
    def write_initial_frames(self):
        """Write initial frames to the video file in a non-blocking way."""
        if self.frame_count < self.total_frames and hasattr(self, 'camera'):
            try:
                self.camera.take_write_snapshot()
            except Exception as e:
                messagebox.showerror("Error", f"An error occurred during measurement: {e}")
                self.finish_measurement()
                return
            self.frame_count += 1
            # Schedule the next frame capture
            self.root.after(1, self.write_initial_frames)  #1ms delay between frames
        else:
            # Capture baseline frame (frame 21) to initialize Real-Time Wear Analyzer ROI & Ai
            if self.realtime_wear_enabled.get() and hasattr(self, 'camera') and self.camera:
                try:
                    base_frame = self.camera.get_frame()
                    if base_frame is not None:
                        self.wear_analyzer.initialize_baseline(base_frame)
                except Exception:
                    pass

            # The Arduino is opened before the message: opening the port resets the board (~2 s)
            try:
                if self.selected_dac == "ArduinoUno":
                    self.measurer = ArduinoUno(port="COM3", baudrate=115200)
                    self.measurer.start()
            except Exception as e:
                messagebox.showerror("Error", f"An error occurred during measurement: {e}")
                self.finish_measurement()
                return

            if getattr(self, 'batch_measured_count', 0) == 0:
                messagebox.showinfo("Start measurement", "If drops are ready, press OK to start measurement.")

            if self.selected_dac == "NIUSB6009":
                self.measurer = NIUSB6009(device_name="Dev1", channel="ai0", sample_rate=1000, samples_per_channel=10000)
                self.measurer.start()

            elif self.selected_dac == "ArduinoUno":
                self.measurer.stop()  # discards the data buffered while the message was open

            elif self.selected_dac == "Test":
                self.rng = np.random.default_rng()

            # Auto-start peristaltic pump if enabled and connected
            if hasattr(self, 'auto_pump_on_measurement') and self.auto_pump_on_measurement.get():
                if hasattr(self, 'pump') and self.pump.is_connected and not self.pump.is_running:
                    try:
                        self.start_pump_flow()
                    except Exception as e:
                        print(f"Warning: could not auto-start pump: {e}")

            # Acquisition runs in a worker thread so the GUI (Stop button) stays responsive
            self.worker_error = None
            self.worker_thread = threading.Thread(target=self._acquisition_loop, daemon=True)
            self.worker_thread.start()
            self.poll_measurement()

    def _acquisition_loop(self):
        """Worker thread: read the photodiode, capture one frame per drop, and process wear in real time."""
        armed = True
        try:
            while self.measuring and self.current_drops < self.total_drops:
                if self.selected_dac == "Test":
                    value = self.rng.random()
                else:
                    value = self.measurer.measure()

                if value is None:  # ArduinoUno may return None on an invalid serial line
                    continue

                if value < self.threshold:
                    if armed:
                        armed = False
                        frame = self.camera.get_frame()
                        drop_idx = self.current_drops + 1
                        self.captured_frames.append({
                            'drop_number': drop_idx,
                            'frame': frame
                        })
                        self.current_drops = drop_idx

                        # Real-time drop-by-drop wear & rupture detection
                        if getattr(self, 'realtime_wear_enabled', None) and self.realtime_wear_enabled.get():
                            if frame is not None:
                                wear_info = self.wear_analyzer.process_drop_frame(frame, drop_number=drop_idx)
                                self.latest_wear_info = wear_info
                                if wear_info.get("is_broken", False):
                                    self.sample_broken_in_realtime = True
                                    break
                else:
                    armed = True
        except Exception as e:
            self.worker_error = e

    def poll_measurement(self):
        """GUI side: refresh the counter, real-time wear status, and detect the end of the worker thread."""
        self.measured_drops_label.config(text=f'Number of drops registered: {self.current_drops}')

        # Update real-time wear widgets if new drop frame was processed
        wear_info = getattr(self, 'latest_wear_info', None)
        if wear_info is not None:
            norm_val = wear_info["normalized_area"]
            wear_pct = wear_info["wear_percent"]
            self.realtime_wear_label.config(
                text=f"Real-Time Normalized Area (Ac-As)/(Ai-As): {norm_val:.3f} | Wear: {wear_pct:.1f}%"
            )
            self.realtime_wear_var.set(wear_pct)
            if wear_info["is_broken"]:
                self.realtime_status_banner.config(
                    text=f"⚡ RUPTURE DETECTED AT DROP #{wear_info['rupture_drop']}! Advancing Carousel...",
                    foreground="#dc2626"
                )
            else:
                self.realtime_status_banner.config(
                    text=f"Measuring Slot #{self.carousel.current_slot} (Drop {wear_info['drop_number']})...",
                    foreground="#0284c7"
                )
            roi_img = wear_info.get("annotated_roi")
            if roi_img is not None and roi_img.size > 0:
                try:
                    rgb_roi = cv2.cvtColor(roi_img, cv2.COLOR_BGR2RGB)
                    pil_roi = Image.fromarray(rgb_roi)
                    tk_roi = ImageTk.PhotoImage(image=pil_roi)
                    self.realtime_preview_label.configure(image=tk_roi, text="")
                    self.realtime_preview_label.image = tk_roi
                except Exception:
                    pass

        if self.worker_thread.is_alive():
            self.root.after(100, self.poll_measurement)
            return

        if self.worker_error is not None:
            messagebox.showerror("Error", f"An error occurred during measurement: {self.worker_error}")
        self.finish_measurement()

    # Save acquired frames to disk
    def save_captured_frames_to_disk(self, target_video_path: Optional[str] = None, keep_camera_open: bool = False):
        """Save the captured frames stored in RAM to disk in a separate thread."""
        if not hasattr(self, 'captured_frames') or not self.captured_frames:
            if not keep_camera_open:
                self.cleanup_camera()
            return

        frames_to_save = list(self.captured_frames)
        self.captured_frames = []  # Empty RAM for next measurement session

        camera_ref = self.camera
        if not keep_camera_open:
            self.camera = None

        def _writer_thread():
            if camera_ref:
                if target_video_path:
                    camera_ref.path_name_save_video = target_video_path
                    camera_ref.set_path_name_save_video()
                camera_ref.save_frames_to_avi(frames_to_save)
                if not keep_camera_open:
                    camera_ref.stop()
                    camera_ref.close_window()

        threading.Thread(target=_writer_thread, daemon=True).start()
    
    def finish_measurement(self):
        """Clean up after single aggregate measurement or advance carousel for 30-sample batch."""
        # Stop and close the measurer task
        if hasattr(self, 'selected_dac') and self.selected_dac in ["NIUSB6009", "ArduinoUno"]:
            if hasattr(self, 'measurer') and self.measurer is not None:
                try:
                    self.measurer.stop()
                    self.measurer.close()
                except Exception:
                    pass

        # Auto-stop peristaltic pump while saving / rotating carousel
        if hasattr(self, 'auto_pump_on_measurement') and self.auto_pump_on_measurement.get():
            if hasattr(self, 'pump') and self.pump.is_connected and self.pump.is_running:
                try:
                    self.stop_pump_flow()
                except Exception as e:
                    print(f"Warning: could not auto-stop pump: {e}")

        # Record current aggregate result in the 30-slot Carousel
        slot_num = self.carousel.current_slot
        broke = bool(getattr(self, 'sample_broken_in_realtime', False))
        status_str = "BROKEN" if broke else ("STABLE" if self.current_drops >= self.total_drops else "STOPPED")
        energy_per_drop_mj = 0.102
        total_energy_mj = self.current_drops * energy_per_drop_mj
        wear_info = getattr(self, 'latest_wear_info', None) or {}
        init_area = wear_info.get("initial_area_px", self.wear_analyzer.initial_area_px)
        final_area = wear_info.get("smoothed_area_px", 0.0)
        norm_final = wear_info.get("normalized_area", 0.0 if broke else 1.0)

        base_vid, ext_vid = os.path.splitext(getattr(self, 'nombrevid', 'measurement.avi'))
        if getattr(self, 'batch_target_count', 1) > 1:
            slot_video_path = f"{base_vid}_slot{slot_num:02d}{ext_vid or '.avi'}"
        else:
            slot_video_path = getattr(self, 'nombrevid', 'measurement.avi')

        self.carousel.record_slot_result(
            slot=slot_num,
            status=status_str,
            drops=self.current_drops,
            energy_mj=total_energy_mj,
            initial_area_px=init_area,
            final_area_px=final_area,
            normalized_final=norm_final,
            video_file=os.path.basename(slot_video_path),
        )
        self.batch_measured_count = getattr(self, 'batch_measured_count', 0) + 1
        self._sync_carousel_badges()

        # Check if we should automatically rotate carousel to the next aggregate and continue
        should_continue_batch = (
            getattr(self, 'auto_carousel_on_rupture', None) is not None
            and self.auto_carousel_on_rupture.get()
            and not getattr(self, 'user_stopped_measurement', False)
            and self.batch_measured_count < getattr(self, 'batch_target_count', 1)
        )

        if should_continue_batch:
            self.save_captured_frames_to_disk(target_video_path=slot_video_path, keep_camera_open=True)
            res = self.carousel.next_slot()
            self.carousel.slot_results[res["slot"]]["status"] = "MEASURING"
            self._sync_carousel_badges()
            self.realtime_status_banner.config(
                text=f"Rotated to Slot #{res['slot']} (Laser={'ALIGNED' if res['laser_aligned'] else 'OK'}). Starting next sample...",
                foreground="#16a34a"
            )
            # Reset for next aggregate in batch
            self.wear_analyzer.reset()
            self.latest_wear_info = None
            self.sample_broken_in_realtime = False
            self.current_drops = 0
            self.measuring = True
            self.frame_count = 0
            self.root.after(250, self.write_initial_frames)
            return

        # Batch or single measurement finished completely
        self.measuring = False
        self.stop_measurement_button.config(state=tk.DISABLED)
        self.start_measurement_button.config(state=tk.NORMAL)
        self.save_captured_frames_to_disk(target_video_path=slot_video_path, keep_camera_open=False)

        if getattr(self, 'batch_target_count', 1) > 1 and self.batch_measured_count > 1:
            summary_csv = f"{base_vid}_30_Aggregates_Summary.csv"
            try:
                self.export_carousel_results_csv(summary_csv)
            except Exception:
                pass
            messagebox.showinfo(
                "Batch Measurement Complete",
                f"Automatically measured {self.batch_measured_count} aggregates.\n"
                f"Last sample ({status_str}): {self.current_drops} drops ({total_energy_mj:.2f} mJ).\n"
                f"Summary saved to:\n{summary_csv}"
            )
        else:
            if broke:
                messagebox.showinfo(
                    "Aggregate Rupture Detected",
                    f"Real-time camera analysis detected aggregate breakdown at {self.current_drops} drops "
                    f"(Energy = {total_energy_mj:.2f} mJ)."
                )
            elif self.current_drops >= self.total_drops:
                messagebox.showinfo("Measurement Complete", f"Successfully recorded {self.current_drops} drops.")
            else:
                messagebox.showinfo("Measurement Stopped", f"Measurement stopped after recording {self.current_drops} drops.")
                

    def stop_measurement(self):
        """Stop the measurement."""
        self.user_stopped_measurement = True
        # Set flag to stop the measurement process
        self.measuring = False

        # Auto-stop peristaltic pump
        if hasattr(self, 'auto_pump_on_measurement') and self.auto_pump_on_measurement.get():
            if hasattr(self, 'pump') and self.pump.is_connected and self.pump.is_running:
                try:
                    self.stop_pump_flow()
                except Exception:
                    pass
    
#Functions of the drop energy tab
    def start_simulation(self):
        g = 9.81  # Gravitational acceleration (m/s^2)
        
        dt = 0.0001 # Time step (s)

        # Set the initial conditions
        rho_w = float(self.water_density.get())  # Water density (kg/m^3)
        rho_a = float(self.air_density.get()) #Air density (Kg/m^3)
        C_d = float(self.drag_coefficient.get())  # Drag coefficient (dimensionless)
        distTOT = 0.01 * float(self.drop_height.get())  # Drop height (m)
        mass = 0.000001 * float(self.drops_weight.get())  # Drop weight (kg)
        
        a = np.pi * (3/4 * mass / rho_w / np.pi)**(2/3) # Cross-sectional area of the drop (assumed spherical) (m^2)
        
        ''' --- START OF APPROXIMATE SOLUTION ----'''
        # Set the simulation parameters        
        Fg = mass * g * (1- rho_a / rho_w) # Gravitational force reduced by buoyancy force(N)
        
        # Initialize arrays to store time, distance, velocity, acceleration, and drag force    
        time_list = [0.0]
        dist_list = [0.0]
        vel_list = [0.0]
        nrg_list = [0.0]
        accl_list = []
        dragF_list = []
        
        i = 0
        while True:
            df = -0.5 * C_d * rho_a * a * vel_list[i]**2
            acc = (df + Fg) / mass
            dragF_list.append(df)
            accl_list.append(acc)

            v_next = vel_list[i] + dt * acc
            vel_list.append(v_next)
            nrg_list.append(0.5 * mass * (vel_list[i]**2))

            d_next = dist_list[i] + dt * vel_list[i] + 0.5 * acc * (dt**2)
            dist_list.append(d_next)
            time_list.append(time_list[i] + dt)
            
            if (dist_list[i] > distTOT) or (i>100000):
                # Stop the simulation if the drop has reached the aggregate
                    
                # Converts array at the end
                dist = np.array(dist_list)
                vel = np.array(vel_list)
                nrg = np.array(nrg_list)

                # Clear any existing plot
                for widget in self.simulation_plot_frame.winfo_children():
                    widget.destroy()
                
                # Create a new matplotlib figure
                self.fig = Figure(figsize=(6, 4), dpi=100)
                self.ax = self.fig.add_subplot(111)
                
                # Plot the data
                self.ax.plot(dist*100, vel, linewidth=1.0) 
                self.ax.set_title(f"Water Drop Energy = {1000 * (nrg[i] + nrg[i-1]) / 2:.5f} mJ", fontsize=16)
                self.ax.set_xlabel('Distance (cm)', fontsize=12)
                self.ax.set_ylabel('Drop velocity (m/s)', fontsize=12)
                self.ax.grid(True)

                # Create a canvas to display the figure in Tkinter
                self.canvas = FigureCanvasTkAgg(self.fig, master=self.simulation_plot_frame)
                self.canvas.draw()
                self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
                
                break
            i += 1
        ''' --- END OF APPROXIMATE SOLUTION ----'''        
        
#Functions of the video processing tab
    def load_video_folder(self):
        """Load a video file and process it."""
        self.video_folder_path = fd.askdirectory(
            title="Select Video Folder",
            mustexist=True
        )
        if not self.video_folder_path:
            return  # User cancelled the file dialog
        
        # Get all video files in the selected folder
        self.video_files = [f for f in os.listdir(self.video_folder_path) if f.lower().endswith(('.mp4', '.avi', '.mov'))]
        if not self.video_files:
            messagebox.showerror("Error", "No video files found in the selected folder.")
            return
        self.video_selection_dropdown['values'] = self.video_files
        self.hole_area_check.config(state='normal')  # Enable the checkbox
        self.hole_area_input.config(state='normal')  # Enable the input field

    def check_action(self):
        """Enable or disable the video selection dropdown based on the checkbox state."""
        if self.hole_area_check.instate(['selected']):
            self.video_selection_dropdown.config(state='disabled')
            self.process_videos_button.config(state=tk.NORMAL)
        else:
            self.video_selection_dropdown.config(state='readonly')
            self.process_videos_button.config(state=tk.DISABLED)        

    def process_videos(self):
        """
        Process the selected video to set the hole area
        """     
        # If the user opted to use the typed-in hole area directly, start batch processing
        if self.hole_area_check.instate(['selected']):
            # Clear right panel
            for w in self.video_output_frame.winfo_children():
                w.destroy()
            self.start_processing_all_videos()
            return

        if self.canvas_hole_area:
            self.canvas_hole_area.pack_forget()
            self.canvas_hole_area = None
        if self.video_label_hole_area:
            self.video_label_hole_area.pack_forget()
            self.video_label_hole_area = None
            if hasattr(self, 'slider') and self.slider:
                self.slider.pack_forget()
            # Only hide the video processing confirm if it exists
            if hasattr(self, 'hole_area_confirm_button') and self.hole_area_confirm_button:
                self.hole_area_confirm_button.pack_forget()

        # Load video
        self.cap = cv2.VideoCapture(os.path.join(self.video_folder_path, self.video_selection.get()))
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.current_frame_idx = 0

        # Frame display the video video for hole area selection
        self.video_label_hole_area = tk.Label(self.video_output_frame)
        self.video_label_hole_area.pack()

        # Slider to navigate between frames
        self.slider = ttk.Scale(
            self.video_output_frame,
            from_=0,
            to=self.total_frames - 1,
            orient="horizontal",
            command=self.on_slider_move,
            length=400
        )
        self.slider.pack(pady=10)

        # Confirmation button for selecting frame (distinct from threshold confirm)
        self.hole_area_confirm_button = tk.Button(
            self.video_output_frame, 
            text="Confirm", 
            command=self.confirm_frame_for_hole_area_selection
        )
        self.hole_area_confirm_button.pack(pady=5)



        # Show the first frame
        self.show_frame(0)

        

        
        

        



    def on_slider_move(self, val):
        """When the slider is moved, show the corresponding frame"""
        frame_idx = int(float(val))
        self.current_frame_idx = frame_idx
        self.show_frame(frame_idx)

    def show_frame(self, frame_idx):
        """Show a frame in the label"""
        img = self.get_frame(frame_idx)
        if img is None:
            return
        self.selected_image_hole_area = img
        imgtk = ImageTk.PhotoImage(image=img)
        self.video_label_hole_area.imgtk = imgtk
        self.video_label_hole_area.configure(image=imgtk)

    def get_frame(self, frame_idx):
        """Return the frame at position frame_idx"""
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self.cap.read()
        if not ret:
            return None
        # Transform from BGR (OpenCV) to RGB (PIL)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(frame)

    def confirm_frame_for_hole_area_selection(self):
        """Finalize the frame and pass to canvas"""
        # Hide video and slider widgets
        self.video_label_hole_area.pack_forget()
        self.slider.pack_forget()
        if hasattr(self, 'hole_area_confirm_button') and self.hole_area_confirm_button:
            self.hole_area_confirm_button.pack_forget()

        # Create canvas
        self.canvas_hole_area = tk.Canvas(self.video_output_frame, 
                                width=self.selected_image_hole_area.width, 
                                height=self.selected_image_hole_area.height
                                )
        self.canvas_hole_area.pack()

        # Show the image as background
        self.bg_image = ImageTk.PhotoImage(self.selected_image_hole_area)
        self.canvas_hole_area.create_image(0, 0, anchor="nw", image=self.bg_image)

        # Elipse confirmation button
        self.btn_elipse_confirmation = tk.Button(self.video_output_frame, text="Confirm ellipse", command=self.confirm_ellipse)
        self.btn_elipse_confirmation.pack(pady=10)

        self.draw_ellipse_on_hole()


    def draw_ellipse_on_hole(self):
        """Allow the user to draw an ellipse on the canvas to select the hole area"""
        # Ellipse parameters
        self.center = [self.bg_image.width() / 2, self.bg_image.height() / 2]
        self.rx, self.ry = 100, 60
        self.angle = 0
        self.ellipse = None

        # Interaction flags
        self.dragging_center = False
        self.rotating = False
        self.resizing_x = False
        self.resizing_y = False

        # Draw initial ellipse
        self.draw_ellipse()

        # Bind mouse events
        self.canvas_hole_area.bind("<Button-1>", self.on_click)
        self.canvas_hole_area.bind("<B1-Motion>", self.on_drag)
        self.canvas_hole_area.bind("<ButtonRelease-1>", self.on_release)

    def draw_ellipse(self):
        """Draw rotated ellipse as polygon on top of image."""
        if self.ellipse:
            self.canvas_hole_area.delete(self.ellipse)

        points = []
        for t in range(0, 360, 3):  # step = resolution
            x = self.rx * math.cos(math.radians(t))
            y = self.ry * math.sin(math.radians(t))

            # apply rotation
            xr = x * math.cos(math.radians(self.angle)) - y * math.sin(math.radians(self.angle))
            yr = x * math.sin(math.radians(self.angle)) + y * math.cos(math.radians(self.angle))

            points.extend((self.center[0] + xr, self.center[1] + yr))

        self.ellipse = self.canvas_hole_area.create_polygon(points, outline="red", fill="", width=2)

    def on_click(self, event):
        dx, dy = event.x - self.center[0], event.y - self.center[1]
        dist_center = math.hypot(dx, dy)

        if dist_center < 15:
            self.dragging_center = True
        else:
            # Rightmost point (rotation handle)
            edge_x = self.center[0] + self.rx * math.cos(math.radians(self.angle))
            edge_y = self.center[1] + self.rx * math.sin(math.radians(self.angle))
            if abs(event.x - edge_x) < 15 and abs(event.y - edge_y) < 15:
                self.rotating = True
            # Bottom point (resize Y)
            elif abs(event.x - (self.center[0] - self.ry * math.cos(math.radians(self.angle-90)))) < 15 and \
                    abs(event.y - (self.center[1] - self.ry * math.sin(math.radians(self.angle-90)))) < 15:
                self.resizing_y = True
            # Left edge (resize X)
            elif abs(event.x - (self.center[0] - self.rx * math.cos(math.radians(self.angle)))) < 15 and \
                    abs(event.y - (self.center[1] - self.rx * math.sin(math.radians(self.angle)))) < 15:
                self.resizing_x = True

    def on_drag(self, event):
        if self.dragging_center:
            self.center = [event.x, event.y]
        elif self.rotating:
            dx, dy = event.x - self.center[0], event.y - self.center[1]
            self.angle = math.degrees(math.atan2(dy, dx))
        elif self.resizing_x:
            self.rx = abs(event.x - self.center[0])
        elif self.resizing_y:
            self.ry = abs(event.y - self.center[1])

        self.draw_ellipse()

    def on_release(self, event):
        self.dragging_center = False
        self.rotating = False
        self.resizing_x = False
        self.resizing_y = False

    def confirm_ellipse(self):
        """Evaluates the area of the ellipse and saves it to the input field."""
        self.hole_area.set(round(math.pi * self.rx * self.ry))
        # Persist the selected hole area for future runs
        try:
            self.save_hole_area(self.hole_area.get())
        except Exception as e:
            # Non-fatal: keep going even if persistence fails
            messagebox.showwarning("Warning", f"Couldn't save hole area: {e}")
        
        self.canvas_hole_area.pack_forget()
        self.canvas_hole_area = None
        self.btn_elipse_confirmation.pack_forget()
        self.btn_elipse_confirmation = None

        # Clear the panel and start processing all videos
        for w in self.video_output_frame.winfo_children():
            w.destroy()
        self.start_processing_all_videos()

    # -------------------- Batch Video Processing --------------------
    def start_processing_all_videos(self):
        """Process all videos in folder, save processed videos and a combined results table, and plot incrementally."""
        if not getattr(self, 'video_folder_path', None):
            messagebox.showerror("Error", "Please load a video folder first.")
            return
        if not getattr(self, 'video_files', None):
            messagebox.showerror("Error", "No videos found to process.")
            return
        # Disable process button to avoid re-entry
        try:
            self.process_videos_button.config(state=tk.DISABLED)
        except Exception:
            pass

        # Output folder INSIDE selected folder: <selected_basename>_PROC
        base_folder_name = os.path.basename(os.path.normpath(self.video_folder_path))
        out_folder = os.path.join(self.video_folder_path, f"{base_folder_name}_PROC")
        try:
            os.makedirs(out_folder, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Error", f"Cannot create output folder: {e}")
            try:
                self.process_videos_button.config(state=tk.NORMAL)
            except Exception:
                pass
            return
        # Prepare Matplotlib area in the right panel
        for w in self.video_output_frame.winfo_children():
            w.destroy()
        self.proc_fig = Figure(figsize=(6, 4), dpi=100)
        self.proc_ax = self.proc_fig.add_subplot(111)
        # No title (requested)
        self.proc_ax.set_xlabel("Image number")
        self.proc_ax.set_ylabel("Normalized area")
        self.proc_ax.set_ylim(-0.1, 1.1)
        self.proc_ax.grid(True)
        self.proc_canvas = FigureCanvasTkAgg(self.proc_fig, master=self.video_output_frame)
        self.proc_canvas.draw()
        self.proc_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Progress bar
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(self.video_output_frame, variable=self.progress_var, maximum=len(self.video_files))
        self.progress_bar.pack(fill=tk.X, padx=5, pady=5)

        # Cancel button
        self.cancel_processing = False
        self.cancel_button = ttk.Button(self.video_output_frame, text='Cancel', command=self.cancel_video_processing)
        self.cancel_button.pack(padx=5, pady=(0,5))

        results = {}  # video_name -> normalized list (without initial NaNs)
        rupture_points = {}  # video_name -> image number where normalized < 0 (or last)
        Agu = int(self.hole_area.get()) if hasattr(self, 'hole_area') else 4000

        for idx, video_file in enumerate(self.video_files, start=1):
            if self.cancel_processing:
                break
            video_path = os.path.join(self.video_folder_path, video_file)
            try:
                name, areas = self._process_single_video(video_path, out_folder)
            except Exception as e:
                messagebox.showwarning("Warning", f"Error processing {video_file}: {e}")
                continue

            if not areas:
                continue

            image_numbers, normalized = self._compute_normalized_series(areas, Agu, window=5)
            results[name] = normalized

            # Determine rupture point (first image where normalized < 0, else last)
            rupture_idx = None
            for i, val in enumerate(normalized):
                if isinstance(val, float) and not np.isnan(val) and val < 0:
                    rupture_idx = image_numbers[i]
                    break
            if rupture_idx is None:
                rupture_idx = image_numbers[-1] if image_numbers else 0
            rupture_points[name] = rupture_idx

            # Update plot incrementally (skip NaNs already removed)
            self.proc_ax.plot(image_numbers, normalized, label=name, linewidth=1.0)
            # Legend outside plot, smaller font
            self.proc_ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5), fontsize=8, frameon=False)
            self.proc_canvas.draw()
            self.root.update_idletasks()
            # Update progress
            self.progress_var.set(idx)
            self.progress_bar.update()

        processed_videos = len(results)

        rupture_median = None
        if processed_videos > 0:
            try:
                rupture_median = statistics.median(rupture_points.values())
            except Exception:
                rupture_median = None

        # Add vertical line for Rupture if available
        if rupture_median is not None and processed_videos > 0:
            self.proc_ax.axvline(rupture_median, color='black', linestyle='--', label='Rupture')
            self.proc_ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5), fontsize=8, frameon=False)
            self.proc_canvas.draw()

        # Write results table (with rupture)
        try:
            self._write_results_table(results, out_folder, rupture_median, os.path.basename(os.path.normpath(self.video_folder_path)))
        except Exception as e:
            messagebox.showwarning("Warning", f"Couldn't write results table: {e}")

        if self.cancel_processing:
            messagebox.showinfo("Canceled", f"Processing canceled after {processed_videos} videos. Output folder:\n{out_folder}")
        else:
            messagebox.showinfo("Done", f"Processed {processed_videos} videos. Output folder:\n{out_folder}")

        # Re-enable process button
        try:
            self.process_videos_button.config(state=tk.NORMAL)
        except Exception:
            pass
        # Remove cancel button
        try:
            self.cancel_button.config(state=tk.DISABLED)
        except Exception:
            pass

    def _process_single_video(self, video_path: str, out_folder: str):
        """Return (base_name, areas) and write processed video to out_folder."""
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError("Cannot open video")

        # Read up to frame 21
        frame = None
        for _ in range(21):
            ret, frame = cap.read()
            if not ret:
                cap.release()
                raise RuntimeError("Couldn't read initial frames up to 21")

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 40, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            cap.release()
            raise RuntimeError("No contours found in initial frame")
        max_contour = max(contours, key=cv2.contourArea)
        x1, y1, w1, h1 = cv2.boundingRect(max_contour)
        x1, y1 = max(x1 - 20, 0), max(y1 - 20, 0)
        w1 = min(w1 + 40, frame.shape[1] - x1)
        h1 = min(h1 + 40, frame.shape[0] - y1)
        max_area = cv2.contourArea(max_contour)

        base = os.path.splitext(os.path.basename(video_path))[0]
        out_path = os.path.join(out_folder, f"{base}_PROC.avi")
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter(out_path, fourcc, 1.0, (w1, h1))

        areas = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_rec = frame[y1:y1 + h1, x1:x1 + w1]
            gray_rec = cv2.cvtColor(frame_rec, cv2.COLOR_BGR2GRAY)
            _, thr = cv2.threshold(gray_rec, 40, 255, cv2.THRESH_BINARY_INV)
            ctrs, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if ctrs:
                cmax = max(ctrs, key=cv2.contourArea)
                area = cv2.contourArea(cmax)
                if area > max_area:
                    area = max_area
                frame_draw = cv2.drawContours(frame_rec.copy(), [cmax], -1, (0, 255, 0), 2)
            else:
                area = 0.0
                frame_draw = frame_rec
            areas.append(float(area))
            out.write(frame_draw)

        cap.release()
        out.release()
        return base, areas

    def _compute_normalized_series(self, areas, Agu: float, window: int = 5):
        """Return (image_numbers, normalized_values) without initial NaNs; first value forced to 1.
        Uses rolling mean over 'window' frames; denominator = first rolling mean - Agu.
        """
        if not areas:
            return [], []
        arr = np.array(areas, dtype=float)
        n = len(arr)
        rolling_vals = []
        image_numbers = []  # Start numbering at 1 for first valid rolling mean
        for i in range(window - 1, n):  # start at first index with full window
            window_slice = arr[i - window + 1: i + 1]
            rolling_vals.append(float(np.mean(window_slice)))
            image_numbers.append(len(rolling_vals))  # sequential numbering starting at 1
        if not rolling_vals:
            return [], []
        first_mean = rolling_vals[0]
        denom = first_mean - Agu
        if abs(denom) <= 1e-12:
            denom = 1.0
        normalized = [(v - Agu) / denom for v in rolling_vals]
        # Force first value to 1 exactly
        normalized[0] = 1.0
        return image_numbers, normalized

    def _write_results_table(self, results: dict, out_folder: str, rupture_median, folder_basename: str):
        # Determine max length across series
        max_len = max((len(v) for v in results.values()), default=0)
        headers = ["Image number"] + list(results.keys())
        rows = []
        for i in range(max_len):
            row = [i + 1]
            for name in results.keys():
                series = results[name]
                row.append(series[i] if i < len(series) else '')
            rows.append(row)

        # Prefer Excel via pandas if available (lazy import)
        try:
            import pandas as pd  # type: ignore
            # Decide engine explicitly to avoid ambiguity
            try:
                import openpyxl  # type: ignore  # noqa: F401
                excel_engine = "openpyxl"
            except ImportError:
                try:
                    import xlsxwriter  # type: ignore  # noqa: F401
                    excel_engine = "xlsxwriter"
                except ImportError:
                    raise RuntimeError(
                        "Excel export requires 'openpyxl' or 'xlsxwriter'. Install with 'pip install openpyxl'."
                    )

            data = {"Image number": [r[0] for r in rows]}
            for idx, name in enumerate(results.keys()):
                data[name] = [r[idx + 1] for r in rows]
            df = pd.DataFrame(data)
            excel_path = os.path.join(out_folder, "Results_PROC.xlsx")
            try:
                with pd.ExcelWriter(excel_path, engine=excel_engine) as writer:
                    df.to_excel(writer, sheet_name="Results_PROC", index=False)
                    rupture_df = pd.DataFrame([[folder_basename, rupture_median if rupture_median is not None else ""]])
                    rupture_df.to_excel(writer, sheet_name="Rupture", index=False, header=False)
                return
            except Exception as e:
                # Surface Excel-specific failure then fall back to CSV
                try:
                    messagebox.showwarning(
                        "Excel export failed",
                        f"Could not create Excel file (will create CSV instead):\n{e}"
                    )
                except Exception:
                    pass
        except Exception as e:
            # Show warning if pandas or engine not available
            try:
                messagebox.showwarning(
                    "Excel export unavailable",
                    f"Pandas/engine not available (will create CSV instead):\n{e}"
                )
            except Exception:
                pass

        # Fallback to CSV if pandas missing or write failed
        import csv
        csv_path = os.path.join(out_folder, "Results_PROC.csv")
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)
        # Rupture info
        if rupture_median is not None:
            with open(os.path.join(out_folder, "Results_PROC_Rupture.txt"), 'w', encoding='utf-8') as rf:
                rf.write(f"{folder_basename},{rupture_median}\n")

    def cancel_video_processing(self):
        self.cancel_processing = True
        try:
            self.cancel_button.config(state=tk.DISABLED)
        except Exception:
            pass

    

    # ---- Persistence helpers for hole area ----
    def load_hole_area_default(self):
        """Return saved hole area from the app state folder if available, else None."""
        try:
            with open(get_hole_area_file(), "r", encoding="utf-8") as f:
                line = f.readline().strip()
                # Accept int or float in file, but store as int
                val = int(float(line))
                if val > 0:
                    return val
        except FileNotFoundError:
            return None
        except Exception:
            return None
        return None

    def save_hole_area(self, value: int):
        """Persist hole area to the app state folder."""
        with open(get_hole_area_file(), "w", encoding="utf-8") as f:
            f.write(f"{int(value)}\n")

def main():
    """Create and return a launcher with a main_loop() to run the GUI."""
    root = tk.Tk()
    app = WaterDropMethod(root)

    class _Launcher:
        def __init__(self, root_ref, app_ref):
            self._root = root_ref
            self._app = app_ref  # keep a reference to prevent GC

        def main_loop(self):
            self._root.mainloop()

    return _Launcher(root, app)


if __name__ == "__main__":
    main().main_loop()
