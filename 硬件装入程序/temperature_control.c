#include <reg51.h>
#include <absacc.h>

// 定义数据类型
#define u8  unsigned char
#define u16 unsigned int
#define u32 unsigned long  

// 定义端口
#define DT_DA_PORT XBYTE[0xe400]     // 数码管数据端口
#define DT_DI_PORT XBYTE[0xe800]
#define PWM_OUT_PORT XBYTE[0xc400]   // 传感器及PWM输出端口
#define SPT_LOW_INPORT XBYTE[0xc100]
#define SPT_HIG_INPORT XBYTE[0xc200]

// 设定值
int SetValue;

// PID控制参数
float Kp = 0.5f;
float Ki = 0.017f;
float Kd = 0.30f;

// 误差变量
int et = 0;
int et_1 = 0;
int et_2 = 0;

// PID积分和微分项
float integral = 0.0f;
float derivative = 0.0f;

// PWM变量
static float pwm = 0.0f;  

// 显示缓冲区
u8 DispBuff[8] = {0, 0, 0, 0, 1, 1, 1, 7};

// 温度数据
u16 temperature = 0;

// 发送标志
bit send_flag = 0;

// 定时器0初始化
void Timer0_Init(void) {
    TMOD |= 0x01;  // 设置定时器0为模式1 (16位定时器)
    TH0 = 0x3C;    // 设置初值以便定时 50ms (假设晶振频率为11.0592MHz)
    TL0 = 0xB0;
    ET0 = 1;       // 使能定时器0中断
    TR0 = 1;       // 启动定时器0
}

// 串口初始化
void UART_Init(void) {
    SCON = 0x50;   // 设置串口为模式1 (8位UART)
    TMOD |= 0x20;  // 设置定时器1为模式2 (8位自动重装)
    TH1 = 0xFD;    // 波特率9600 (假设晶振频率为11.0592MHz)
    TL1 = 0xFD;
        
    TR1 = 1;       // 启动定时器1
    ES = 1;        // 使能串口中断
    EA = 1;        // 使能全局中断
}

// 发送一个字节
void send_byte(u8 dat) {
    SBUF = dat;
    while (!TI);
    TI = 0;
}

// 发送温度数据
void send_temperature(void) {
    send_byte(0x55);  // 起始字节
    send_byte(0x02);  // 数据类型 (温度)
    send_byte((u8)(temperature >> 8));  // 高字节
    send_byte((u8)(temperature));       // 低字节
    send_byte(0xaa);  // 结束字节
}

// 更新显示
void update_display(void) {
    static u8 CurrentBit = 0;
    u8 SevenSegCode[10] = {0x3F, 0x06, 0x5B, 0x4F, 0x66, 0x6D, 0x7D, 0x07, 0x7F, 0x6F};
    u8 SevenSegBT[8] = {0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80};

    DT_DI_PORT = 0;
    DT_DA_PORT = SevenSegCode[DispBuff[CurrentBit]];
    DT_DI_PORT = SevenSegBT[CurrentBit];

    CurrentBit++;
    if (CurrentBit >= 8) CurrentBit = 0;
}

// 读取传感器数据
u16 read_sensor(void) {
    u16 x;
    *((u8 *)&x + 1) = SPT_LOW_INPORT;
    *((u8 *)&x + 0) = SPT_HIG_INPORT;
    return x;
}

// 限幅函数
float limit_value(float value, float min, float max) {
    if (value > max) return max;
    if (value < min) return min;
    return value;
}

// 更新显示缓冲区
void update_display_buffer(u16 value) {
    // 如果接收到的是放大100倍的值,需要先除以100
    value = value / 100;
    DispBuff[4] = value / 1000;
    value %= 1000;
    DispBuff[5] = value / 100;
    value %= 100;
    DispBuff[6] = value / 10;
    DispBuff[7] = value % 10;
}

// PID控制计算
void PID_Control(void) {
    float pid_output;
    u16 temp;  // 临时变量，用于保存中间结果

    // 读取传感器数据
    temperature = read_sensor();

    // 计算误差
    et_2 = et_1;
    et_1 = et;
    et = SetValue - (int)temperature;

    // 计算积分项 (使用梯形积分法)
    integral += et;
    integral = limit_value(integral, -1000, 1000);  // 应用积分限幅

    // 计算微分项
    derivative = et - et_1;

    // PID控制算法
    pid_output = Kp * et + Ki * integral + Kd * derivative;

    // 更新PWM值
    pwm += pid_output;
    pwm = limit_value(pwm, 0, 255);  // PWM限幅

    // 输出PWM
    PWM_OUT_PORT = (u8)pwm;

    // 使用临时变量更新显示缓冲区
    temp = temperature;
    update_display_buffer(temp);
}

// 处理接收到的数据包
void process_received_packet(u8 *buffer) {
    if (buffer[0] == 0x55 && buffer[1] == 0x01 && buffer[4] == 0xaa) {
        // 解析温度设定值
        SetValue = (buffer[2] << 8) | buffer[3];
    }
}

// 串口中断服务函数
void serial_isr(void) interrupt 4 {
    static u8 rx_buffer[5];  // 接收缓冲区
    static u8 rx_index = 0;

    if (RI) {
        RI = 0;
        rx_buffer[rx_index++] = SBUF;

        // 检查是否接收到完整数据包
        if (rx_index == 5) {
            process_received_packet(rx_buffer);
            rx_index = 0;  // 重置索引
        }
    }
}

// 定时器0中断服务函数
void timer0_isr(void) interrupt 1 {
    // 重装定时器初值
    TH0 = 0x3C;
    TL0 = 0xB0;
    
    send_flag = 1;  // 设置发送标志
}

// 主函数
void main(void) {
    u8 send_counter = 0;
    UART_Init();    // 初始化串口
    Timer0_Init();  // 初始化定时器0
    while (1) {
        PID_Control();
        update_display();
        
        if (send_flag) {
            send_counter++;
            if (send_counter >= 5) {  // 每5个周期发送一次
                send_temperature();
                send_counter = 0;
            }
            send_flag = 0;  // 重置发送标志
        }
        //send_temperature();
    }
}