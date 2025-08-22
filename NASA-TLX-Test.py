import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime

# 定义NASA-TLX的六个维度及其描述
DIMENSIONS = {
    "MD": {
        "name": "Mental Demand (心理需求)",
        "description": "在任务中，您需要进行多少心理和感知活动（如思考、决策、记忆、观察）？"
    },
    "PD": {
        "name": "Physical Demand (身体需求)",
        "description": "在任务中，您需要进行多少身体活动（如操作、移动、控制）？"
    },
    "TD": {
        "name": "Temporal Demand (时间需求)",
        "description": "您在任务中感受到的时间压力有多大？工作节奏是快还是慢？"
    },
    "P": {
        "name": "Performance (绩效水平)",
        "description": "您对自己在这项任务中的表现有多成功？您对自己的表现满意吗？"
    },
    "E": {
        "name": "Effort (努力程度)",
        "description": "为了达到您的任务表现水平，您感觉自己付出了多少努力（脑力上和体力上）？"
    },
    "F": {
        "name": "Frustration (挫折水平)",
        "description": "在任务中，您感觉有多不安全、灰心、烦躁、有压力或恼怒？"
    }
}

# 定义15个配对比较
PAIRS = [
    ("PD", "F"), ("TD", "P"), ("PD", "E"), ("MD", "F"),
    ("E", "F"), ("MD", "P"), ("TD", "F"), ("PD", "P"),
    ("MD", "PD"), ("E", "P"), ("MD", "TD"), ("PD", "TD"),
    ("MD", "E"), ("TD", "E"), ("F", "P")
]


class NasaTlxApp:
    def __init__(self, master):
        self.master = master
        self.master.title("NASA-TLX 负荷评估问卷")
        self.master.geometry("600x800")

        # 初始化数据存储变量
        self.participant_id_var = tk.StringVar()
        self.ratings_vars = {dim: tk.IntVar() for dim in DIMENSIONS}
        self.weights = {dim: 0 for dim in DIMENSIONS}
        self.current_pair_index = 0
        self.selected_weight_var = tk.StringVar()

        # 创建并布局界面
        self.create_widgets()

    def create_widgets(self):
        self.main_frame = ttk.Frame(self.master, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.ratings_frame = ttk.Frame(self.main_frame)
        self.weighting_frame = ttk.Frame(self.main_frame)
        
        self.create_ratings_page()
        self.create_weighting_page()

        self.ratings_frame.pack(fill=tk.BOTH, expand=True)

    def create_ratings_page(self):
        ttk.Label(self.ratings_frame, text="第一部分：维度评分", font=("Helvetica", 16, "bold")).pack(pady=10)
        
        # 新增：ID输入框
        id_frame = ttk.Frame(self.ratings_frame)
        ttk.Label(id_frame, text="请输入被试/任务ID:", font=("Helvetica", 12)).pack(side="left", padx=(0, 5))
        ttk.Entry(id_frame, textvariable=self.participant_id_var, width=30).pack(side="left")
        id_frame.pack(pady=10)

        ttk.Label(self.ratings_frame, text="请在完成任务后，根据您的感受为以下六个维度打分。", wraplength=550).pack(pady=5)

        for key, value in DIMENSIONS.items():
            frame = ttk.Frame(self.ratings_frame, padding=(0, 10))
            ttk.Label(frame, text=value["name"], font=("Helvetica", 12, "bold")).pack(anchor="w")
            ttk.Label(frame, text=value["description"], wraplength=500, justify=tk.LEFT).pack(anchor="w", fill="x")
            scale = ttk.Scale(frame, from_=0, to=100, orient="horizontal", variable=self.ratings_vars[key], length=500)
            scale.pack(pady=5)
            labels_frame = ttk.Frame(frame)
            ttk.Label(labels_frame, text="低").pack(side="left")
            ttk.Label(labels_frame, text="高").pack(side="right")
            labels_frame.pack(fill="x", expand=True)
            frame.pack(fill="x")

        ttk.Button(self.ratings_frame, text="完成评分，进入权重比较", command=self.switch_to_weighting).pack(pady=20)

    def create_weighting_page(self):
        ttk.Label(self.weighting_frame, text="第二部分：权重比较", font=("Helvetica", 16, "bold")).pack(pady=10)
        ttk.Label(self.weighting_frame, text="在每一对中，请选择对您刚才任务的工作负荷贡献更大的维度。", wraplength=550).pack(pady=10)

        self.pair_counter_label = ttk.Label(self.weighting_frame, text="", font=("Helvetica", 12))
        self.pair_counter_label.pack(pady=10)
        self.radio_button1 = ttk.Radiobutton(self.weighting_frame, variable=self.selected_weight_var)
        self.radio_button2 = ttk.Radiobutton(self.weighting_frame, variable=self.selected_weight_var)
        self.radio_button1.pack(anchor="w", padx=50, pady=5)
        self.radio_button2.pack(anchor="w", padx=50, pady=5)
        self.next_button = ttk.Button(self.weighting_frame, text="下一对", command=self.next_pair)
        self.next_button.pack(pady=20)

    def switch_to_weighting(self):
        if not self.participant_id_var.get():
            messagebox.showwarning("缺少ID", "请输入被试或任务ID后再继续。")
            return
        self.ratings_frame.pack_forget()
        self.weighting_frame.pack(fill=tk.BOTH, expand=True)
        self.display_current_pair()

    def display_current_pair(self):
        if self.current_pair_index < len(PAIRS):
            dim1_key, dim2_key = PAIRS[self.current_pair_index]
            self.pair_counter_label.config(text=f"第 {self.current_pair_index + 1} / 15 组")
            self.radio_button1.config(text=DIMENSIONS[dim1_key]["name"], value=dim1_key)
            self.radio_button2.config(text=DIMENSIONS[dim2_key]["name"], value=dim2_key)
            self.selected_weight_var.set("")
        else:
            self.show_calculate_button()

    def next_pair(self):
        selected = self.selected_weight_var.get()
        if not selected:
            messagebox.showwarning("未选择", "请选择一个对负荷贡献更大的维度。")
            return
        self.weights[selected] += 1
        self.current_pair_index += 1
        self.display_current_pair()
        
    def show_calculate_button(self):
        self.pair_counter_label.config(text="所有权重比较已完成！")
        self.radio_button1.pack_forget()
        self.radio_button2.pack_forget()
        self.next_button.pack_forget()
        ttk.Button(self.weighting_frame, text="计算并查看最终负荷分数", command=self.calculate_and_save_results).pack(pady=20)

    def calculate_and_save_results(self):
        """计算最终分数，保存到文件，并弹窗显示"""
        weighted_sum = sum(self.ratings_vars[key].get() * self.weights[key] for key in DIMENSIONS)
        final_score = weighted_sum / 15
        
        # 准备用于显示和保存的文本
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        participant_id = self.participant_id_var.get()
        
        log_text = (
            "=================================================\n"
            f"评估时间: {timestamp}\n"
            f"被试/任务 ID: {participant_id}\n"
            "-------------------------------------------------\n"
            f"最终加权工作负荷分数 (Weighted TLX Score): {final_score:.2f}\n"
            "-------------------------------------------------\n"
            "详细数据:\n"
        )
        for key, value in DIMENSIONS.items():
            log_text += (
                f"  - {value['name']}:\n"
                f"    评分: {self.ratings_vars[key].get()}\n"
                f"    权重: {self.weights[key]}\n"
            )
        log_text += "=================================================\n\n"
        
        # 写入文件
        try:
            with open("nasa_tlx_results.txt", "a", encoding="utf-8") as f:
                f.write(log_text)
            save_confirmation = "\n结果已成功保存到 nasa_tlx_results.txt 文件中。"
        except Exception as e:
            save_confirmation = f"\n\n警告：结果保存失败！\n错误: {e}"
            messagebox.showerror("文件保存错误", f"无法写入结果文件 'nasa_tlx_results.txt'。\n请检查文件权限。\n\n错误详情: {e}")
        
        # 弹窗显示结果
        display_text = f"被试ID: {participant_id}\n最终加权工作负荷分数为: {final_score:.2f}" + save_confirmation
        messagebox.showinfo("评估结果", display_text)
        
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = NasaTlxApp(root)
    root.mainloop()