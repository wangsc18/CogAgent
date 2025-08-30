import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import json
import csv
import random

# --- NASA-TLX 定义 ---
NASA_DIMENSIONS = {
    "MD": {"name": "Mental Demand (心理需求)", "description": "在任务中，您需要进行多少心理和感知活动（如思考、决策、记忆、观察）？"},
    "PD": {"name": "Physical Demand (身体需求)", "description": "在任务中，您需要进行多少身体活动（如操作、移动、控制）？"},
    "TD": {"name": "Temporal Demand (时间需求)", "description": "您在任务中感受到的时间压力有多大？工作节奏是快还是慢？"},
    "P":  {"name": "Performance (绩效水平)", "description": "您对自己在这项任务中的表现有多成功？您对自己的表现满意吗？"},
    "E":  {"name": "Effort (努力程度)", "description": "为了达到您的任务表现水平，您感觉自己付出了多少努力（脑力上和体力上）？"},
    "F":  {"name": "Frustration (挫折水平)", "description": "在任务中，您感觉有多不安全、灰心、烦躁、有压力或恼怒？"}
}
NASA_PAIRS = [
    ("PD", "F"), ("TD", "P"), ("PD", "E"), ("MD", "F"), ("E", "F"),
    ("MD", "P"), ("TD", "F"), ("PD", "P"), ("MD", "PD"), ("E", "P"),
    ("MD", "TD"), ("PD", "TD"), ("MD", "E"), ("TD", "E"), ("F", "P")
]

# --- UEQ 定义 (--- 修正1：添加中文翻译 ---) ---
UEQ_ITEMS = [
    {'id': 1, 'term_neg': 'annoying', 'term_pos': 'enjoyable', 'term_neg_cn': '烦人的', 'term_pos_cn': '令人愉快的', 'scale': 'Attractiveness'},
    {'id': 2, 'term_neg': 'not understandable', 'term_pos': 'understandable', 'term_neg_cn': '难懂的', 'term_pos_cn': '易懂的', 'scale': 'Perspicuity'},
    {'id': 3, 'term_neg': 'creative', 'term_pos': 'dull', 'term_neg_cn': '有创造性的', 'term_pos_cn': '呆板的', 'scale': 'Novelty'},
    {'id': 4, 'term_neg': 'difficult to learn', 'term_pos': 'easy to learn', 'term_neg_cn': '难学的', 'term_pos_cn': '易学的', 'scale': 'Perspicuity'},
    {'id': 5, 'term_neg': 'valuable', 'term_pos': 'inferior', 'term_neg_cn': '有价值的', 'term_pos_cn': '劣质的', 'scale': 'Stimulation'},
    {'id': 6, 'term_neg': 'boring', 'term_pos': 'exciting', 'term_neg_cn': '无聊的', 'term_pos_cn': '令人兴奋的', 'scale': 'Stimulation'},
    {'id': 7, 'term_neg': 'not interesting', 'term_pos': 'interesting', 'term_neg_cn': '无趣的', 'term_pos_cn': '有趣的', 'scale': 'Stimulation'},
    {'id': 8, 'term_neg': 'unpredictable', 'term_pos': 'predictable', 'term_neg_cn': '不可预知的', 'term_pos_cn': '可预知的', 'scale': 'Dependability'},
    {'id': 9, 'term_neg': 'slow', 'term_pos': 'fast', 'term_neg_cn': '慢的', 'term_pos_cn': '快的', 'scale': 'Efficiency'},
    {'id': 10, 'term_neg': 'conventional', 'term_pos': 'inventive', 'term_neg_cn': '传统的', 'term_pos_cn': '有创意的', 'scale': 'Novelty'},
    {'id': 11, 'term_neg': 'obstructive', 'term_pos': 'supportive', 'term_neg_cn': '阻碍的', 'term_pos_cn': '辅助的', 'scale': 'Dependability'},
    {'id': 12, 'term_neg': 'good', 'term_pos': 'bad', 'term_neg_cn': '好的', 'term_pos_cn': '坏的', 'scale': 'Attractiveness'},
    {'id': 13, 'term_neg': 'complicated', 'term_pos': 'easy', 'term_neg_cn': '复杂的', 'term_pos_cn': '简单的', 'scale': 'Perspicuity'},
    {'id': 14, 'term_neg': 'unlikable', 'term_pos': 'pleasing', 'term_neg_cn': '不讨人喜欢的', 'term_pos_cn': '讨人喜欢的', 'scale': 'Attractiveness'},
    {'id': 15, 'term_neg': 'usual', 'term_pos': 'leading edge', 'term_neg_cn': '普通的', 'term_pos_cn': '前沿的', 'scale': 'Novelty'},
    {'id': 16, 'term_neg': 'unpleasant', 'term_pos': 'pleasant', 'term_neg_cn': '不愉快的', 'term_pos_cn': '愉快的', 'scale': 'Attractiveness'},
    {'id': 17, 'term_neg': 'not secure', 'term_pos': 'secure', 'term_neg_cn': '不安全的', 'term_pos_cn': '安全的', 'scale': 'Dependability'},
    {'id': 18, 'term_neg': 'motivating', 'term_pos': 'demotivating', 'term_neg_cn': '有激励作用的', 'term_pos_cn': '令人泄气的', 'scale': 'Stimulation'},
    {'id': 19, 'term_neg': 'meets expectations', 'term_pos': 'does not meet expectations', 'term_neg_cn': '符合预期', 'term_pos_cn': '不符合预期', 'scale': 'Dependability'},
    {'id': 20, 'term_neg': 'inefficient', 'term_pos': 'efficient', 'term_neg_cn': '低效的', 'term_pos_cn': '高效的', 'scale': 'Efficiency'},
    {'id': 21, 'term_neg': 'clear', 'term_pos': 'confusing', 'term_neg_cn': '清晰的', 'term_pos_cn': '令人困惑的', 'scale': 'Perspicuity'},
    {'id': 22, 'term_neg': 'impractical', 'term_pos': 'practical', 'term_neg_cn': '不实用的', 'term_pos_cn': '实用的', 'scale': 'Efficiency'},
    {'id': 23, 'term_neg': 'organized', 'term_pos': 'cluttered', 'term_neg_cn': '有序的', 'term_pos_cn': '杂乱的', 'scale': 'Efficiency'},
    {'id': 24, 'term_neg': 'attractive', 'term_pos': 'ugly', 'term_neg_cn': '有吸引力的', 'term_pos_cn': '难看的', 'scale': 'Attractiveness'},
    {'id': 25, 'term_neg': 'friendly', 'term_pos': 'unfriendly', 'term_neg_cn': '友好的', 'term_pos_cn': '不友好的', 'scale': 'Attractiveness'},
    {'id': 26, 'term_neg': 'conservative', 'term_pos': 'innovative', 'term_neg_cn': '保守的', 'term_pos_cn': '创新的', 'scale': 'Novelty'}
]
UEQ_CSV_HEADER = [f'Item{i+1}' for i in range(26)]


class NasaTlxUeqApp:
    def __init__(self, master):
        self.master = master
        self.master.title("NASA-TLX & UEQ 综合评估问卷")
        self.master.geometry("800x900")

        self.participant_id_var = tk.StringVar()
        self.system_condition_var = tk.StringVar()
        
        self.tlx_ratings_vars = {dim: tk.IntVar() for dim in NASA_DIMENSIONS}
        self.tlx_weights = {dim: 0 for dim in NASA_DIMENSIONS}
        self.current_pair_index = 0
        self.selected_weight_var = tk.StringVar()
        
        self.ueq_vars = {item['id']: tk.IntVar(value=4) for item in UEQ_ITEMS}
        self.ueq_display_reversal = {} # 用于记录每个问题项在显示时是否被反转

        self.create_widgets()

    def create_widgets(self):
        self.main_frame = ttk.Frame(self.master, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        self.tlx_ratings_frame = ttk.Frame(self.main_frame)
        self.tlx_weighting_frame = ttk.Frame(self.main_frame)
        self.ueq_frame = ttk.Frame(self.main_frame)
        
        self.create_tlx_ratings_page()
        self.create_tlx_weighting_page()
        self.create_ueq_page()

        self.tlx_ratings_frame.pack(fill=tk.BOTH, expand=True)

    def create_tlx_ratings_page(self):
        ttk.Label(self.tlx_ratings_frame, text="第一部分：NASA-TLX 维度评分", font=("Helvetica", 16, "bold")).pack(pady=10)
        
        id_frame = ttk.Frame(self.tlx_ratings_frame)
        ttk.Label(id_frame, text="被试ID:", font=("Helvetica", 12)).pack(side="left", padx=(0, 5))
        ttk.Entry(id_frame, textvariable=self.participant_id_var, width=20).pack(side="left")
        ttk.Label(id_frame, text="系统条件:", font=("Helvetica", 12)).pack(side="left", padx=(10, 5))
        ttk.Entry(id_frame, textvariable=self.system_condition_var, width=20).pack(side="left")
        id_frame.pack(pady=10)

        for key, value in NASA_DIMENSIONS.items():
            frame = ttk.Frame(self.tlx_ratings_frame, padding=(0, 10))
            ttk.Label(frame, text=value["name"], font=("Helvetica", 12, "bold")).pack(anchor="w")
            ttk.Label(frame, text=value["description"], wraplength=700, justify=tk.LEFT).pack(anchor="w", fill="x")
            scale = ttk.Scale(frame, from_=0, to=100, orient="horizontal", variable=self.tlx_ratings_vars[key], length=700)
            scale.pack(pady=5)
            labels_frame = ttk.Frame(frame)
            ttk.Label(labels_frame, text="低").pack(side="left")
            ttk.Label(labels_frame, text="高").pack(side="right")
            labels_frame.pack(fill="x", expand=True)
            frame.pack(fill="x")

        ttk.Button(self.tlx_ratings_frame, text="完成评分，进入负荷权重比较", command=self.switch_to_weighting).pack(pady=20)

    def create_tlx_weighting_page(self):
        ttk.Label(self.tlx_weighting_frame, text="第二部分：NASA-TLX 权重比较", font=("Helvetica", 16, "bold")).pack(pady=10)
        ttk.Label(self.tlx_weighting_frame, text="在每一对中，请选择对您刚才任务的工作负荷贡献更大的维度。", wraplength=650).pack(pady=10)

        self.pair_counter_label = ttk.Label(self.tlx_weighting_frame, text="", font=("Helvetica", 12))
        self.pair_counter_label.pack(pady=10)
        self.radio_button1 = ttk.Radiobutton(self.tlx_weighting_frame, variable=self.selected_weight_var)
        self.radio_button2 = ttk.Radiobutton(self.tlx_weighting_frame, variable=self.selected_weight_var)
        self.radio_button1.pack(anchor="center", padx=50, pady=5)
        self.radio_button2.pack(anchor="center", padx=50, pady=5)
        
        self.next_button = ttk.Button(self.tlx_weighting_frame, text="下一对", command=self.next_pair)
        self.next_button.pack(pady=20)
    
    def create_ueq_page(self):
        ttk.Label(self.ueq_frame, text="第三部分：用户体验问卷 (UEQ)", font=("Helvetica", 16, "bold")).pack(pady=10)
        ttk.Label(self.ueq_frame, text="请根据您对刚才使用系统的整体感受，在每一对形容词之间选择最符合您看法的位置。", wraplength=750).pack(pady=5)

        canvas = tk.Canvas(self.ueq_frame)
        scrollbar = ttk.Scrollbar(self.ueq_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # --- 修正2：启用鼠标滚轮滚动 ---
        def _on_mousewheel(event):
            # 兼容Windows, macOS和Linux的滚轮事件
            if event.num == 5 or event.delta < 0:
                canvas.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:
                canvas.yview_scroll(-1, "units")
        
        # 将滚轮事件绑定到Canvas和内部的Frame上，确保鼠标在任何位置都能滚动
        for widget in [canvas, scrollable_frame]:
            widget.bind("<MouseWheel>", _on_mousewheel) # For Windows and macOS
            widget.bind("<Button-4>", _on_mousewheel)   # For Linux scroll up
            widget.bind("<Button-5>", _on_mousewheel)   # For Linux scroll down
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        shuffled_ueq_items = random.sample(UEQ_ITEMS, len(UEQ_ITEMS))

        for item_data in shuffled_ueq_items:
            item_id = item_data['id']
            # 随机决定正负形容词的左右位置，并记录
            is_reversed = random.choice([True, False])
            self.ueq_display_reversal[item_id] = is_reversed
            
            # --- 修正1：使用中文标签 ---
            if is_reversed:
                left_term, right_term = item_data['term_pos_cn'], item_data['term_neg_cn']
            else:
                left_term, right_term = item_data['term_neg_cn'], item_data['term_pos_cn']

            frame = ttk.Frame(scrollable_frame, padding=(0, 8))
            label_frame = ttk.Frame(frame)
            ttk.Label(label_frame, text=left_term.capitalize(), font=("Helvetica", 11)).pack(side="left")
            ttk.Label(label_frame, text=right_term.capitalize(), font=("Helvetica", 11)).pack(side="right")
            label_frame.pack(fill="x", expand=True, padx=20)
            radio_frame = ttk.Frame(frame)
            for i in range(1, 8):
                rb = ttk.Radiobutton(radio_frame, text=str(i), variable=self.ueq_vars[item_id], value=i)
                rb.pack(side="left", padx=15, expand=True)
                # 将滚轮事件也绑定到Radiobutton上，确保滚动无死角
                rb.bind("<MouseWheel>", _on_mousewheel)
                rb.bind("<Button-4>", _on_mousewheel)
                rb.bind("<Button-5>", _on_mousewheel)
            radio_frame.pack(pady=2)
            ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=5)
            frame.pack(fill="x")
        
        ttk.Button(self.ueq_frame, text="完成所有问卷，计算并保存结果", command=self.calculate_and_save_results).pack(pady=20, side="bottom")

    def switch_to_weighting(self):
        if not self.participant_id_var.get() or not self.system_condition_var.get():
            messagebox.showwarning("信息不全", "请输入被试ID和系统条件后再继续。")
            return
        self.tlx_ratings_frame.pack_forget()
        self.tlx_weighting_frame.pack(fill=tk.BOTH, expand=True)
        self.display_current_pair()

    def switch_to_ueq(self):
        self.tlx_weighting_frame.pack_forget()
        self.ueq_frame.pack(fill=tk.BOTH, expand=True)

    def display_current_pair(self):
        if self.current_pair_index < len(NASA_PAIRS):
            dim1_key, dim2_key = NASA_PAIRS[self.current_pair_index]
            self.pair_counter_label.config(text=f"第 {self.current_pair_index + 1} / {len(NASA_PAIRS)} 组")
            self.radio_button1.config(text=NASA_DIMENSIONS[dim1_key]["name"], value=dim1_key)
            self.radio_button2.config(text=NASA_DIMENSIONS[dim2_key]["name"], value=dim2_key)
            self.selected_weight_var.set("")
        else:
            self.show_ueq_button()

    def next_pair(self):
        selected = self.selected_weight_var.get()
        if not selected:
            messagebox.showwarning("未选择", "请选择一个对负荷贡献更大的维度。")
            return
        self.tlx_weights[selected] += 1
        self.current_pair_index += 1
        self.display_current_pair()
        
    def show_ueq_button(self):
        self.pair_counter_label.config(text="所有权重比较已完成！")
        self.radio_button1.pack_forget()
        self.radio_button2.pack_forget()
        self.next_button.pack_forget()
        ttk.Button(self.tlx_weighting_frame, text="完成权重比较，进入用户体验问卷 (UEQ)", command=self.switch_to_ueq).pack(pady=20)

    def get_formatted_ueq_data(self):
        raw_scores = {item_id: var.get() for item_id, var in self.ueq_vars.items()}
        formatted_scores = []
        for i in range(1, 27):
            score = raw_scores[i]
            # 检查该问题在本次显示时是否被反转了
            if self.ueq_display_reversal.get(i, False):
                score = 8 - score
            
            # 根据UEQ官方定义，部分词条的“正向”词在左边，原始值为1
            # 例如 id=3, creative(1) / dull(7)。如果用户选了1，它代表“创造性”
            # 我们的计分需要将所有分数都校准为“正向形容词得分高”
            # 官方工具会自动处理，我们只需保证“左=1, 右=7”的原始分即可
            original_item = next((item for item in UEQ_ITEMS if item['id'] == i), None)
            
            # 检查原始定义中，正向词是否在左边 (term_pos在term_neg的位置)
            # 例如: id=3, creative(pos)/dull(neg), id=5, valuable(pos)/inferior(neg)
            # 这些词条的评分需要反转才能符合“数值越高越正面”的原则
            # 官方Excel工具的说明： "For the items 3, 5, 12, 17, 19, 21, 23, 24, 25 the order of the scales is positive-negative."
            # 这意味着这些ID的原始评分需要反转。1分代表最好，7分代表最差。
            # 为了能直接粘贴进工具，我们需要将这些ID的分数进行 8-score 的转换。
            if original_item['term_pos'] == original_item['term_neg']: # 这是一个简化的检查，实际上应该是看哪个词在左边
                 # 实际上，官方工具只需要我们提供1-7的原始分，它自己会处理反转
                 # 我们的`self.ueq_display_reversal`已经保证了无论怎么显示，1都代表最左边，7都代表最右边。
                 # 所以，我们只需要提交这个校准后的分数即可。
                 pass


            formatted_scores.append(score)
        return formatted_scores

    def calculate_and_save_results(self):
        tlx_weighted_sum = sum(self.tlx_ratings_vars[key].get() * self.tlx_weights[key] for key in NASA_DIMENSIONS)
        final_tlx_score = tlx_weighted_sum / 15 if sum(self.tlx_weights.values()) > 0 else 0

        # 新增：收集每个维度的原始分数
        tlx_raw_scores = {key: self.tlx_ratings_vars[key].get() for key in NASA_DIMENSIONS}

        ueq_data_row = self.get_formatted_ueq_data()
        
        participant_id = self.participant_id_var.get()
        system_condition = self.system_condition_var.get()
        
        try:
            with open("assessment_results_summary.txt", "a", encoding="utf-8") as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write("=================================================\n")
                f.write(f"评估时间: {timestamp}\n")
                f.write(f"被试 ID: {participant_id}\n")
                f.write(f"系统条件: {system_condition}\n")
                f.write("-------------------------------------------------\n")
                f.write("NASA-TLX 各维度原始分数:\n")
                for key, value in NASA_DIMENSIONS.items():
                    f.write(f"{value['name']}: {tlx_raw_scores[key]}\n")
                f.write("-------------------------------------------------\n")
                f.write(f"最终加权工作负荷分数 (TLX Score): {final_tlx_score:.2f}\n")
                f.write("-------------------------------------------------\n")
                f.write("UEQ 原始评分 (按Item 1-26顺序, 已校准左右):\n")
                f.write(f"{ueq_data_row}\n")
                f.write("=================================================\n\n")

            csv_file = "ueq_data_for_analysis.csv"
            try:
                with open(csv_file, 'x', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(['Participant_ID', 'System_Condition', 'TLX_Score'] + UEQ_CSV_HEADER)
            except FileExistsError:
                pass

            with open(csv_file, "a", newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([participant_id, system_condition, f"{final_tlx_score:.2f}"] + ueq_data_row)
            
            save_confirmation = "\n结果已成功保存到 .txt 和 .csv 文件中。"

        except Exception as e:
            save_confirmation = f"\n\n警告：结果保存失败！\n错误: {e}"
            messagebox.showerror("文件保存错误", f"无法写入结果文件。\n请检查文件权限。\n\n错误详情: {e}")
        
        display_text = (
            f"被试ID: {participant_id}\n"
            f"系统条件: {system_condition}\n\n"
            f"NASA-TLX 负荷分数: {final_tlx_score:.2f}\n"
            f"UEQ 问卷已记录。"
            f"{save_confirmation}"
        )
        messagebox.showinfo("评估完成", display_text)
        
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = NasaTlxUeqApp(root)
    root.mainloop()