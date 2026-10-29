import cv2

class CameraOpenCV:
    def __init__(self, fps=None, width=None, height=None):
        self.fps = fps if fps is not None else 1
        self.width = width if width is not None else 640
        self.height = height if height is not None else 480
        self.path_name_save_video = "captured_video.avi"
        self.fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        self.cap = None
        self.out = None

    def set_path_name_save_video(self):
        if self.out is not None:
            self.out.release()
        self.out = cv2.VideoWriter(self.path_name_save_video, self.fourcc, self.fps, (self.width, self.height))

    def start(self, device=None):
        self.device = device if device is not None else 0
        self.cap = cv2.VideoCapture(self.device)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open camera device {self.device}")
        self.cap.set(cv2.CAP_PROP_TEMPERATURE, 6500)
        # Keep only the latest frame in the driver buffer (ignored by some drivers)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def preview_camera(self, winname=None):
        if not self.cap or not self.cap.isOpened():
            raise RuntimeError("Camera is not active")
        ret, frame = self.cap.read()
        if not ret or frame is None:
            raise ValueError("Failed to capture frame")
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), cv2.waitKey(1)

    def take_write_snapshot(self):
        if self.out is None:
            self.set_path_name_save_video()
        ret, frame = self.cap.read()
        if not ret or frame is None:
            raise ValueError("Failed to read frame from camera")
        self.out.write(frame)

    def get_frame(self):
        if not self.cap or not self.cap.isOpened():
            raise RuntimeError("Camera is not active")
        ret, frame = self.cap.read()
        if not ret or frame is None:
            raise ValueError("Failed to read frame from camera")
        return frame

    def save_frames_to_avi(self, frames):
        """Escribe una lista de fotogramas en el archivo AVI especificado."""
        if not frames:
            return

        if self.out is None:
            self.set_path_name_save_video()

        for item in frames:
            frame = item['frame'] if isinstance(item, dict) else item
            self.out.write(frame)

        self.out.release()
        self.out = None

    def close_window(self):
        cv2.destroyAllWindows()

    def stop(self):
        """Libera la cámara y el escritor de video de forma segura."""
        if self.cap is not None:
            if self.cap.isOpened():
                self.cap.release()
            self.cap = None
            
        if self.out is not None:
            self.out.release()
            self.out = None