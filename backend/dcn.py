"""Exact Deep & Cross Network architecture from notebook cell 124."""
import torch
from torch import nn


class CrossLayer(nn.Module):
    def __init__(self, input_dim):
        super().__init__()
        self.weight = nn.Parameter(torch.zeros(input_dim))
        self.bias = nn.Parameter(torch.zeros(input_dim))

    def forward(self, x0, x):
        return x0 * torch.sum(x * self.weight, dim=1, keepdim=True) + self.bias + x


class DeepCrossNetwork(nn.Module):
    def __init__(self, input_dim, cross_layers=3):
        super().__init__()
        self.cross_layers = nn.ModuleList([CrossLayer(input_dim) for _ in range(cross_layers)])
        self.deep = nn.Sequential(
            nn.Linear(input_dim, 256), nn.ReLU(), nn.BatchNorm1d(256), nn.Dropout(.30),
            nn.Linear(256, 128), nn.ReLU(), nn.BatchNorm1d(128), nn.Dropout(.25),
            nn.Linear(128, 64), nn.ReLU(), nn.Dropout(.20),
        )
        self.output = nn.Linear(input_dim + 64, 1)

    def forward(self, x):
        cross = x
        for layer in self.cross_layers:
            cross = layer(x, cross)
        return self.output(torch.cat([cross, self.deep(x)], dim=1))
