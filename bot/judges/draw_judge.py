# bot/judges/draw_judge.py

def get_refine_prompt() -> str:
    """
    负责控制 AI 照片“质感”的终极精修提示词。
    如果要改变照片的画风（比如从真人写实变成二次元动漫风，或者改变摄影器材），都在这里改！
    """
    return (
        "将图片中的人物转化为极具真实感的真人。建立一张看起来像是用 iPhone 自拍或随手拍摄的照片。"
        "照片中不应有刻意清晰的主体或完美的构图，而应是一张随意、无意识的日常快照。"
        "照片应因轻微移动而略带模糊，光影（如路灯或自然光）均匀且真实。宽高比呈现为 9:16 的视觉感。"
        "照片绝对不能看起来像是人工智能生成的，必须呈现出 100% 真人拍摄的生活质感。"
    )

def get_ref_image_prompt(description: str) -> str:
    """有参考垫图时的动作/场景变换提示词"""
    return f"请严格保持参考图中人物的五官特征、气质和基础设定，将其置入以下生活场景中，并根据场景调整动作与服装：{description}"

def get_base_gen_prompt(description: str) -> str:
    """无参考图时的基础生成提示词"""
    return f"一张照片。人物细节：{description}"