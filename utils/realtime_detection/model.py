import torch
import torch.nn as nn

try:
    from torchvision.models.video import r3d_18, R3D_18_Weights
    HAS_TORCHVISION_R3D = True
except ImportError:
    HAS_TORCHVISION_R3D = False

class SimpleResNet3D(nn.Module):
    """
    如果torchvision没有r3d_18，则用简化版ResNet3D结构。
    """
    def __init__(self, num_classes=3):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv3d(3, 64, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm3d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool3d((1,2,2)),
            nn.Conv3d(64, 128, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm3d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool3d((2,2,2)),
            nn.Conv3d(128, 256, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm3d(256),
            nn.ReLU(inplace=True),
            nn.AdaptiveAvgPool3d((1,1,1))
        )
        self.classifier = nn.Linear(256, num_classes)
    def forward(self, x):
        # x: [B, 3, T, H, W]
        x = self.features(x)
        x = x.flatten(1)
        x = self.classifier(x)
        return x

def get_resnet3d(num_classes=3, pretrained=False):
    """
    返回一个适用于本任务的ResNet3D模型，输入为[batch, 32, 3, 112, 112]，输出为3类。
    优先使用torchvision.models.video.r3d_18。
    """
    if HAS_TORCHVISION_R3D:
        if pretrained:
            weights = R3D_18_Weights.DEFAULT
        else:
            weights = None
        model = r3d_18(weights=weights)
        model.fc = nn.Linear(model.fc.in_features, num_classes)
        return model
    else:
        return SimpleResNet3D(num_classes=num_classes)

# if __name__ == "__main__":
#     # 验证模型输入输出
#     model = get_resnet3d(num_classes=3, pretrained=False)
#     x = torch.randn(2, 32, 3, 112, 112)
#     y = model(x)
#     print(f"输入: {x.shape}, 输出: {y.shape}") 