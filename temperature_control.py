import tkinter as tk
from tkinter import ttk
import serial
import time
import sqlite3
from threading import Thread, Lock
from queue import Queue
from datetime import datetime
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import webbrowser
import pygame


# 串口初始化
def init_serial():
    global ser
    try:
        ser = serial.Serial('COM3', 9600, timeout=1)
    except serial.SerialException as e:
        print(f"Serial error: {e}")
        ser = None


# 初始化串口
init_serial()

# 初始化pygame混音器
pygame.mixer.init()

# 创建SQLite数据库连接
conn = sqlite3.connect('temperature_data.db', check_same_thread=False)
cursor = conn.cursor()

# 创建表
table_name = 'data_' + time.strftime('%Y%m%d%H%M%S')
cursor.execute(f'''
    CREATE TABLE IF NOT EXISTS {table_name} (
        timestamp TEXT,
        temperature REAL
    )
''')
conn.commit()

# 创建数据队列
data_queue = Queue()
data_lock = Lock()  # 添加数据锁


# 更新状态标签
def update_status(message):
    status_label.config(text=message)


# 播放音频文件
def play_sound(file):
    pygame.mixer.music.load(file)
    pygame.mixer.music.play()


# 发送设定温度,并检测设定范围
def send_set_temp(set_temp):
    global ser
    if ser and ser.is_open:
        if set_temp < 15:
            set_temp = 50
            play_sound('low_temp_alert.wav')  # 播放低温警告音频
            update_status("温度过低! 调整为 50 °C 并播放警告音.")
        elif set_temp > 150:
            set_temp = 50
            play_sound('high_temp_alert.wav')  # 播放高温警告音频
            update_status("温度过高! 调整为 50 °C 并播放警告音.")
        else:
            update_status(f"设定温度为 {set_temp} °C")

        # 如果需要,进行单位转换,例如放大100倍
        set_temp = int(set_temp * 100)
        data = bytearray([0x55, 0x01, (set_temp >> 8) & 0xFF, set_temp & 0xFF, 0xaa])
        ser.write(data)
    else:
        update_status("串口未打开")


# 打开串口
def open_serial():
    global ser
    try:
        if ser is None or not ser.is_open:
            ser = serial.Serial('COM3', 9600, timeout=1)
            update_status("打开串口 COM3")
            start_reading()  # 每次打开串口后重新启动读取线程
        else:
            update_status("串口已经打开")
    except Exception as e:
        update_status(f"错误: {str(e)}")


# 关闭串口
def close_serial():
    global ser
    if ser and ser.is_open:
        ser.close()
        ser = None
        update_status("关闭串口")
    else:
        update_status("串口未打开")


# 更新显示数据
def update_display():
    global conn, cursor, table_name, data_queue, display_data

    try:
        while not data_queue.empty():
            timestamp, temp = data_queue.get()

            with data_lock:
                cursor.execute(f'''
                    INSERT INTO {table_name} (timestamp, temperature)
                    VALUES (?, ?)
                ''', (timestamp, temp))
                conn.commit()

            display_data.insert('', 'end', values=(timestamp, temp))

            # 自动滚动到最新的数据
            display_data.yview_moveto(1)

    except Exception as e:
        print(f"Error: {str(e)}")

    root.after(100, update_display)


# 读取温度数据
def read_temperature():
    global ser, data_queue, data_lock
    try:
        while True:
            if ser and ser.is_open:
                if ser.in_waiting:
                    data = ser.read(5)
                    if data[0] == 0x55 and data[1] == 0x02 and data[4] == 0xaa:
                        temp = (data[2] << 8) | data[3]
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        temp = temp / 100.0
                        with data_lock:
                            # 将数据放入队列
                            data_queue.put((timestamp, temp))
                        update_status(f"读取温度: {temp} °C")
                time.sleep(0.1)  # 每次读取数据后休眠0.1秒，控制读取频率
            else:
                time.sleep(1)  # 如果串口未打开，休眠1秒后重试
    except Exception as e:
        update_status(f"错误: {str(e)}")


# 查询历史数据
def query_data():
    global cursor
    query_window = tk.Toplevel(root)
    query_window.title("查询数据")

    ttk.Label(query_window, text="选择表:").grid(column=0, row=0, padx=10, pady=10)
    tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
    table_names = [table[0] for table in tables]
    table_combo = ttk.Combobox(query_window, values=table_names)
    table_combo.grid(column=1, row=0, padx=10, pady=10)

    def show_data():
        selected_table = table_combo.get()
        if selected_table:
            query_result = cursor.execute(f"SELECT * FROM {selected_table}").fetchall()
            for row in query_result:
                query_display.insert('', 'end', values=row)

            # 绘制历史数据图表
            if query_result:
                timestamps = [datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S') for row in query_result]
                temperatures = [row[1] for row in query_result]

                fig = go.Figure(go.Scatter(x=timestamps, y=temperatures, mode='lines+markers', name='Temperature'))

                fig.update_layout(
                    title='历史温度数据',
                    xaxis_title='时间',
                    yaxis_title='温度',
                    yaxis=dict(
                        autorange=True
                    ),
                    xaxis=dict(
                        rangeslider=dict(visible=True),
                    )
                )

                fig.show()
        else:
            update_status("请选择一个表")

    ttk.Button(query_window, text="查询", command=show_data).grid(column=0, row=1, padx=10, pady=10)

    query_display = ttk.Treeview(query_window, columns=("时间", "温度"), show='headings')
    query_display.heading("时间", text="时间")
    query_display.heading("温度", text="温度")
    query_display.grid(column=0, row=2, columnspan=2, padx=10, pady=10)


# 实时显示温度数据图表
def open_graph():
    app = Dash(__name__)

    app.layout = html.Div(
        children=[
            html.H1(children='实时温度监控'),
            dcc.Graph(id='live-graph'),
            dcc.Interval(
                id='interval-component',
                interval=1 * 1000,  # 以毫秒为单位的间隔时间
                n_intervals=0
            )
        ]
    )

    @app.callback(Output('live-graph', 'figure'), [Input('interval-component', 'n_intervals')])
    def update_graph_live(n):
        with sqlite3.connect('temperature_data.db') as dash_conn:
            dash_cursor = dash_conn.cursor()
            dash_cursor.execute(f"SELECT * FROM {table_name} ORDER BY timestamp ASC LIMIT 500")
            rows = dash_cursor.fetchall()

        if not rows:
            return go.Figure()  # 如果没有数据，返回一个空的图表

        timestamps = [datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S') for row in rows]
        start_time = timestamps[0]
        temperatures = [row[1] for row in rows]
        time_deltas = [(timestamp - start_time).total_seconds() for timestamp in timestamps]

        fig = go.Figure(go.Scatter(x=time_deltas, y=temperatures, mode='lines+markers', name='Temperature'))

        # 设置全局纵坐标范围
        y_range = [min(temperatures) - 5, max(temperatures) + 5]  # 在最小和最大温度的基础上各加5度，以便更好显示

        fig.update_layout(
            title='实时温度监控',
            xaxis_title='时间 (s)',
            yaxis_title='温度',
            yaxis=dict(
                range=y_range  # 设置固定的纵坐标范围
            ),
            xaxis=dict(
                rangeslider=dict(visible=True),  # 显示范围滑块
                range=[max(0, max(time_deltas) - 20), max(time_deltas)]  # 保持x轴显示最近20秒的数据
            )
        )

        return fig

    # 启动Dash服务器
    dash_thread = Thread(target=lambda: app.run_server(debug=False, port=8050))
    dash_thread.daemon = True
    dash_thread.start()

    # 打开浏览器
    webbrowser.open('http://localhost:8050')


# GUI应用程序
root = tk.Tk()
root.title("温度控制系统")
root.configure(bg='#e0e0e0')

# 创建顶部控制框架
control_frame = ttk.Frame(root)
control_frame.pack(pady=20)

# 创建设定温度输入框及按钮
ttk.Label(control_frame, text="设定温度 (°C):").grid(row=0, column=0, padx=10, pady=10)
set_temp_entry = ttk.Entry(control_frame, width=10)
set_temp_entry.grid(row=0, column=1, padx=10, pady=10)

set_temp_button = ttk.Button(control_frame, text="发送设定", command=lambda: send_set_temp(float(set_temp_entry.get())))
set_temp_button.grid(row=0, column=2, padx=10, pady=10)

# 创建串口控制按钮
serial_control_frame = ttk.Frame(root)
serial_control_frame.pack(pady=20)

open_button = ttk.Button(serial_control_frame, text="打开串口", command=open_serial)
open_button.grid(row=0, column=0, padx=10, pady=10)

close_button = ttk.Button(serial_control_frame, text="关闭串口", command=close_serial)
close_button.grid(row=0, column=1, padx=10, pady=10)

# 创建状态标签
status_label = ttk.Label(root, text="等待命令...")
status_label.pack(pady=10)

# 创建实时数据显示框架
data_frame = ttk.Frame(root)
data_frame.pack(pady=20)

# 创建数据表格
columns = ("时间", "温度")
display_data = ttk.Treeview(data_frame, columns=columns, show="headings")
display_data.heading("时间", text="时间")
display_data.heading("温度", text="温度")
display_data.pack(pady=10)

# 创建历史数据查询按钮
query_button = ttk.Button(root, text="查询历史数据", command=query_data)
query_button.pack(pady=10)
# 添加“打开实时数据绘图”按钮
graph_button = ttk.Button(root, text="打开实时数据绘图", command=open_graph)
graph_button.pack(pady=10)

# 设置主题
style = ttk.Style()
style.theme_use('clam')  # 选择主题
style.configure('TLabel', font=('Helvetica', 12))
style.configure('TButton', font=('Helvetica', 12))
style.configure('TEntry', font=('Helvetica', 12))

# 你也可以为某些组件设置特定的样式
style.configure('Control.TFrame', background='#f0f0f0')
style.configure('Status.TLabel', background='#d0d0d0', font=('Helvetica', 12, 'bold'))


# 启动读取温度数据的线程
def start_reading():
    read_thread = Thread(target=read_temperature)
    read_thread.daemon = True
    read_thread.start()


# 更新显示
update_display()

# 运行主循环
root.mainloop()
