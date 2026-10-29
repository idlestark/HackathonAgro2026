# -*- coding: utf-8 -*-
"""
Created on May 12 2022

@author: Alberto

Tomo una serie de datos del fotodiodo leidos de la NI-USB6009, genero un gráfico de dato en función de número de medida y activo el cursor para seleccionar el valor umbral de medida, luego se dibuja la linea correspondiente y si la selección es adecuada el programa finaliza escribiendo el valor del umbral seleccionado en un archivo; en caso de no ser adecuada, se vuelve a activar el cursor para seleccionar un nuevo valor
"""


import nidaqmx
import numpy as np
import matplotlib.pyplot as plt


umbral = 0.15 #Valor umbral del fotodiodo por debajo del cual se adquiere una imagen 
medidas = 5000
ss = 1000

task = nidaqmx.Task()
task.ai_channels.add_ai_voltage_chan("Dev1/ai0")
task.timing.cfg_samp_clk_timing(ss,samps_per_chan=10000)



input("\nUna vez que tengas listo el gotero, presioná Enter para comenzar la recolección de datos...")

task.start()
i = 0
valores=[]
while i < medidas:
        
    value =task.read()
       
    valores.append([i,value])
    
    
    
    i += 1

valores = np.array(valores)
task.stop()
task.close()





def onclick(event):
    global iy
    iy = event.ydata
    
    fig.canvas.mpl_disconnect(cid)
    #plt.close(1)

    return

isok = 'n'
while isok == 'n':
    plt.ion()
    fig = plt.figure(1)
    ax = fig.add_subplot(111)
    ax.plot(valores[:,0],valores[:,1])
    fig.canvas.draw()
    fig.canvas.flush_events()
    cid = fig.canvas.mpl_connect('button_press_event', onclick)
    plt.pause(10)
    
    
    #input("Presioná Enter una vez que hayas hecho click sobre el gráfico en la posición que creas que debe situarse el umbral")
    
    
    ax.plot(valores[:,0],valores[:,1]*0+iy)
    plt.pause(10)

    resp= input("\n¿Estás de acuerdo con el umbral seleccionado? Sí (s); No (n): ")
    if resp == 's':
        isok = 's'
    
    plt.close()

f = open("umbral.txt", "w")

f.write(f"{iy}\n")

f.close()







