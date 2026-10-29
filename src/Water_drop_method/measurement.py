# -*- coding: utf-8 -*-
"""
Created on Thu Feb 25 14:24:05 2021

@author: Alberto

Tomo una serie de datos datos leidos de la NI-USB6009 y los almaceno en un archivo mientras que la cámara está registrando (sin hacer nada)
PRUEBO sin configurar el "sample_mode" porque así supuestamente funciona "on-demand".
Le quito el wait.key que parece que enlentece el while.
"""

import time
import nidaqmx
import cv2 as cv
import numpy as np
from tkinter import Tk
import tkinter.filedialog as fd


#medidas = input("¿Cuántas medidas querés que adquiera el fotodiodo?: ") #Esto se usa cuando la adquisición se define en términos de medidas del fotodiodo.
gotas = 500 #int(input("\n¿Cuántas gotas querés adquirir?: "))


umbral =  np.loadtxt('umbral.txt') #Valor umbral del fotodiodo por debajo del cual se adquiere una imagen. 
retraso = 0.05 #retraso entre la detección de la gota y la adquisición de la imagen.
ss = 1000 #muestrtas por segundo que va a tomar el fotodiodo.
cuadin = 20 #número de cuadros iniciales del video para que la cámara ajuste sus parámetros automáticos.


#Create an instance of tkinter window
win= Tk()
nombrevid = fd.asksaveasfilename(defaultextension = 'avi')
win.destroy()



cap = cv.VideoCapture(0)
if not cap.isOpened():
    print("Cannot open camera")

    exit()
fourcc = cv.VideoWriter_fourcc('M','J','P','G')#cv.VideoWriter_fourcc(*'XVID')
out = cv.VideoWriter(nombrevid, fourcc, 1.0, (640,  480))

#Fijo la temperatura de la imagen
cap.set(cv.CAP_PROP_TEMPERATURE,6500)

#Escribo varios cuadros en el video para tener una referencia inicial
for i in range(cuadin):

    ret, frame = cap.read()
    out.write(frame)
    time.sleep(retraso)


task = nidaqmx.Task()
task.ai_channels.add_ai_voltage_chan("Dev1/ai0")
task.timing.cfg_samp_clk_timing(ss,samps_per_chan=1000000)
     


i = 0
j = 0

input("\nUna vez que tengas las gotas listas, presioná Enter")

starttime = time.time()
print("\n")#+str(starttime))

task.start()
#while i < medidas: #Esto se usa cuando la adquisición se define en términos de medidas del fotodiodo.
while j < gotas:
        
    value =task.read()
       
    

    
    
    i += 1

    
    #Este es el sector de la cámara
    if value < umbral:
        task.stop()
        time.sleep(retraso)
        
         # Capture a frame
        ret, frame = cap.read()
        
             
        #Acá se escribe la imagen           
        out.write(frame)
        j += 1
        print(str(j))
        task.start()
        

 
endtime = time.time()
 
totaltime = endtime - starttime

print("\n"+str(totaltime))



task.stop()
task.close()

# When everything done, release the capture
cap.release()
out.release()




