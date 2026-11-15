import tkinter as tk
from tkinter import messagebox
import cv2
import PIL.Image, PIL.ImageTk
import os


VIDEO_SOURCE = 0

class App:
    def __init__(self, window, window_title, video_source=VIDEO_SOURCE):
        self.window = window
        self.window.title(window_title)
        self.video_source = video_source


        self.vid = MyVideoCapture(self.video_source)


        self.canvas = tk.Canvas(window, width=413, height=532)
        self.canvas.pack()


        self.btn_toggle_source = tk.Button(window, text="Source Video", width=50, command=self.changeVideoSource)
        self.btn_toggle_source.pack(anchor=tk.CENTER, expand=True)


        self.label = tk.Label(window, text="Entrer le Matricule:")
        self.label.pack()
        self.entry = tk.Entry(window)
        self.entry.pack()


        self.btn_snapshot = tk.Button(window, text="Prendre une Photo", width=50, command=self.snapshot)
        self.btn_snapshot.pack(anchor=tk.CENTER, expand=True)


        self.delay = 15
        self.update()

        self.window.mainloop()

    def changeVideoSource(self):

        self.video_source = (self.video_source + 1) % 2


        self.vid = MyVideoCapture(self.video_source)

    def snapshot(self):

        id = self.entry.get()
        if id == "":
            return


        ret, frame = self.vid.get_frame()

        if os.path.exists(f"{id}.jpg"):

            messagebox.showerror("Error", "Une Photo avec ce matricule existe déjà!!")
        elif ret:



            cropped_frame = frame[0:532, 0:413]
            cv2.imwrite(f"{id}.jpg", cv2.cvtColor(cropped_frame, cv2.COLOR_RGB2BGR))

            messagebox.showinfo("Success!!", "Photo pour Matricule: {} Enregistrée".format(id))


    def update(self):

        ret, frame = self.vid.get_frame()

        if ret:
            self.photo = PIL.ImageTk.PhotoImage(image=PIL.Image.fromarray(frame))
            self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)

        self.window.after(self.delay, self.update)

class MyVideoCapture:
    def __init__(self, video_source=VIDEO_SOURCE):

        self.vid = cv2.VideoCapture(video_source)
        if not self.vid.isOpened():
            raise ValueError("Unable to open video source", video_source)






        self.width = self.vid.get(cv2.CAP_PROP_FRAME_WIDTH)
        self.height = self.vid.get(cv2.CAP_PROP_FRAME_HEIGHT)

    def get_frame(self):
        if self.vid.isOpened():
            ret, frame = self.vid.read()

            if ret:

                return (ret, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            else:
                return (ret, None)
        else:
            return (ret, None)


    def __del__(self):
        if self.vid.isOpened():
            self.vid.release()


App(tk.Tk(), "Application Photo")
