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

class SerialCommunication:
    def __init__(self, port='COM3', baud_rate=9600):
        self.port = port
        self.baud_rate = baud_rate
        self.ser = None
        self.init_serial()

    def init_serial(self):
        try:
            self.ser = serial.Serial(self.port, self.baud_rate, timeout=1)
        except serial.SerialException as e:
            print(f"Serial error: {e}")
            self.ser = None

    def open_serial(self):
        try:
            if self.ser is None or not self.ser.is_open:
                self.ser = serial.Serial(self.port, self.baud_rate, timeout=1)
                return "打开串口成功"
            else:
                return "串口已经打开"
        except Exception as e:
            return f"错误: {str(e)}"

    def close_serial(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None
            return "关闭串口成功"
        else:
            return "串口未打开"

    def send_data(self, data):
        if self.ser and self.ser.is_open:
            self.ser.write(data)
            return "数据发送成功"
        else:
            return "串口未打开"

    def read_data(self, size=5):
        if self.ser and self.ser.is_open and self.ser.in_waiting:
            return self.ser.read(size)
        return None

class DatabaseManager:
    def __init__(self, db_name='temperature_data.db'):
        self.db_name = db_name
        self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.table_name = 'data_' + time.strftime('%Y%m%d%H%M%S')
        self.create_table()

    def create_table(self):
        self.cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                timestamp TEXT,
                temperature REAL
            )
        ''')
        self.conn.commit()

    def insert_data(self, timestamp, temperature):
        self.cursor.execute(f'''
            INSERT INTO {self.table_name} (timestamp, temperature)
            VALUES (?, ?)
        ''', (timestamp, temperature))
        self.conn.commit()

    def query_tables(self):
        return [table[0] for table in self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()]

    def query_data(self, table_name):
        return self.cursor.execute(f"SELECT * FROM {table_name}").fetchall()

class SoundManager:
    def __init__(self):
        pygame.mixer.init()

    def play_sound(self, file):
        pygame.mixer.music.load(file)
        pygame.mixer.music.play()

class TemperatureControlApp:
    def __init__(self, root):
        self.root = root
        self.serial_comm = SerialCommunication()
        self.db_manager = DatabaseManager()
        self.sound_manager = SoundManager()
        self.data_queue = Queue()
        self.data_lock = Lock()
        self.display_data = None
        self.status_label = None
        self.setup_gui()
        self.update_display()
        self.start_reading()

    def setup_gui(self):
        self.root.title("温度控制系统")
        self.root.configure(bg='#e0e0e0')

        control_frame = ttk.Frame(self.root)
        control_frame.pack(pady=20)

        ttk.Label(control_frame, text="设定温度 (°C):").grid(row=0, column=0, padx=10, pady=10)
        self.set_temp_entry = ttk.Entry(control_frame, width=10)
        self.set_temp_entry.grid(row=0, column=1, padx=10, pady=10)

        set_temp_button = ttk.Button(control_frame, text="发送设定", command=self.send_set_temp)
        set_temp_button.grid(row=0, column=2, padx=10, pady=10)

        serial_control_frame = ttk.Frame(self.root)
        serial_control_frame.pack(pady=20)

        open_button = ttk.Button(serial_control_frame, text="打开串口", command=self.open_serial)
        open_button.grid(row=0, column=0, padx=10, pady=10)

        close_button = ttk.Button(serial_control_frame, text="关闭串口", command=self.close_serial)
        close_button.grid(row=0, column=1, padx=10, pady=10)

        self.status_label = ttk.Label(self.root, text="等待命令...")
        self.status_label.pack(pady=10)

        data_frame = ttk.Frame(self.root)
        data_frame.pack(pady=20)

        columns = ("时间", "温度")
        self.display_data = ttk.Treeview(data_frame, columns=columns, show="headings")
        self.display_data.heading("时间", text="时间")
        self.display_data.heading("温度", text="温度")
        self.display_data.pack(pady=10)

        query_button = ttk.Button(self.root, text="查询历史数据", command=self.query_data)
        query_button.pack(pady=10)

        graph_button = ttk.Button(self.root, text="打开实时数据绘图", command=self.open_graph)
        graph_button.pack(pady=10)

        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', font=('Helvetica', 12))
        style.configure('TButton', font=('Helvetica', 12))
        style.configure('TEntry', font=('Helvetica', 12))
        style.configure('Control.TFrame', background='#f0f0f0')
        style.configure('Status.TLabel', background='#d0d0d0', font=('Helvetica', 12, 'bold'))

    def update_status(self, message):
        self.status_label.config(text=message)

    def open_serial(self):
        status_message = self.serial_comm.open_serial()
        self.update_status(status_message)

    def close_serial(self):
        status_message = self.serial_comm.close_serial()
        self.update_status(status_message)

    def send_set_temp(self):
        try:
            set_temp = float(self.set_temp_entry.get())
        except ValueError:
            self.update_status("请输入有效的温度值")
            return

        if set_temp < 15:
            set_temp = 50
            self.sound_manager.play_sound('low_temp_alert.wav')
            self.update_status("温度过低! 调整为 50 °C 并播放警告音.")
        elif set_temp > 150:
            set_temp = 50
            self.sound_manager.play_sound('high_temp_alert.wav')
            self.update_status("温度过高! 调整为 50 °C 并播放警告音.")
        else:
            self.update_status(f"设定温度为 {set_temp} °C")

        set_temp = int(set_temp * 100)
        data = bytearray([0x55, 0x01, (set_temp >> 8) & 0xFF, set_temp & 0xFF, 0xaa])
        status_message = self.serial_comm.send_data(data)
        self.update_status(status_message)

    def update_display(self):
        try:
            while not self.data_queue.empty():
                timestamp, temp = self.data_queue.get()

                with self.data_lock:
                    self.db_manager.insert_data(timestamp, temp)

                self.display_data.insert('', 'end', values=(timestamp, temp))
                self.display_data.yview_moveto(1)

        except Exception as e:
            self.update_status(f"Error: {str(e)}")

        self.root.after(100, self.update_display)

    def read_temperature(self):
        try:
            while True:
                data = self.serial_comm.read_data()
                if data and data[0] == 0x55 and data[1] == 0x02 and data[4] == 0xaa:
                    temp = (data[2] << 8) | data[3]
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    temp = temp / 100.0
                    with self.data_lock:
                        self.data_queue.put((timestamp, temp))
                    self.update_status(f"读取温度: {temp} °C")
                time.sleep(0.1)
        except Exception as e:
            self.update_status(f"错误: {str(e)}")

    def query_data(self):
        query_window = tk.Toplevel(self.root)
        query_window.title("查询数据")

        ttk.Label(query_window, text="选择表:").grid(column=0, row=0, padx=10, pady=10)
        table_names = self.db_manager.query_tables()
        table_combo = ttk.Combobox(query_window, values=table_names)
        table_combo.grid(column=1, row=0, padx=10, pady=10)

        query_display = ttk.Treeview(query_window, columns=("时间", "温度"), show='headings')
        query_display.heading("时间", text="时间")
        query_display.heading("温度", text="温度")
        query_display.grid(column=0, row=2, columnspan=2, padx=10, pady=10)

        def show_data():
            selected_table = table_combo.get()
            if selected_table:
                query_result = self.db_manager.query_data(selected_table)
                for row in query_result:
                    query_display.insert('', 'end', values=row)

                if query_result:
                    timestamps = [datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S') for row in query_result]
                    temperatures = [row[1] for row in query_result]

                    fig = go.Figure(go.Scatter(x=timestamps, y=temperatures, mode='lines+markers', name='Temperature'))
                    fig.update_layout(
                        title='历史温度数据',
                        xaxis_title='时间',
                        yaxis_title='温度',
                        yaxis=dict(autorange=True),
                        xaxis=dict(rangeslider=dict(visible=True)),
                    )
                    fig.show()
            else:
                self.update_status("请选择一个表")

        ttk.Button(query_window, text="查询", command=show_data).grid(column=0, row=1, padx=10, pady=10)

    def open_graph(self):
        app = Dash(__name__)
        app.layout = html.Div(
            children=[
                html.H1(children='实时温度监控'),
                dcc.Graph(id='live-graph'),
                dcc.Interval(id='interval-component', interval=1 * 1000, n_intervals=0),
            ]
        )

        @app.callback(Output('live-graph', 'figure'), [Input('interval-component', 'n_intervals')])
        def update_graph_live(n):
            with sqlite3.connect('temperature_data.db') as dash_conn:
                dash_cursor = dash_conn.cursor()
                dash_cursor.execute(f"SELECT * FROM {self.db_manager.table_name} ORDER BY timestamp ASC LIMIT 500")
                rows = dash_cursor.fetchall()

            if not rows:
                return go.Figure()

            timestamps = [datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S') for row in rows]
            start_time = timestamps[0]
            temperatures = [row[1] for row in rows]
            time_deltas = [(timestamp - start_time).total_seconds() for timestamp in timestamps]

            fig = go.Figure(go.Scatter(x=time_deltas, y=temperatures, mode='lines+markers', name='Temperature'))
            y_range = [min(temperatures) - 5, max(temperatures) + 5]

            fig.update_layout(
                title='实时温度监控',
                xaxis_title='时间 (s)',
                yaxis_title='温度',
                yaxis=dict(range=y_range),
                xaxis=dict(
                    rangeslider=dict(visible=True),
                    range=[max(0, max(time_deltas) - 20), max(time_deltas)],
                ),
            )
            return fig

        dash_thread = Thread(target=lambda: app.run_server(debug=False, port=8050))
        dash_thread.daemon = True
        dash_thread.start()
        webbrowser.open('http://localhost:8050')

    def start_reading(self):
        read_thread = Thread(target=self.read_temperature)
        read_thread.daemon = True
        read_thread.start()

if __name__ == "__main__":
    root = tk.Tk()
    app = TemperatureControlApp(root)
    root.mainloop()