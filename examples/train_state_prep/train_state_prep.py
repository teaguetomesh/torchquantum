"""
MIT License

Copyright (c) 2020-present TorchQuantum Authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import torch
import torch.optim as optim
import argparse

import torchquantum as tq
from torch.optim.lr_scheduler import CosineAnnealingLR

import random
import numpy as np


class QModel(tq.QuantumModule):
    def __init__(self):
        super().__init__()
        self.n_wires = 2
        self.u3_0 = tq.U3(has_params=True, trainable=True)
        self.u3_1 = tq.U3(has_params=True, trainable=True)
        self.cu3_0 = tq.CU3(has_params=True, trainable=True)
        self.cu3_1 = tq.CU3(has_params=True, trainable=True)
        self.u3_2 = tq.U3(has_params=True, trainable=True)
        self.u3_3 = tq.U3(has_params=True, trainable=True)

    def forward(self, q_device: tq.QuantumDevice):
        q_device.reset_states(1)
        self.u3_0(q_device, wires=0)
        self.u3_1(q_device, wires=1)
        self.cu3_0(q_device, wires=[0, 1])
        self.u3_2(q_device, wires=0)
        self.u3_3(q_device, wires=1)
        self.cu3_1(q_device, wires=[1, 0])


def train(target_state, device, model, optimizer):
    model(device)
    result_state = device.get_states_1d()[0]

    # compute the state infidelity
    loss = 1 - torch.dot(result_state, target_state).abs() ** 2

    optimizer.zero_grad()
    loss.backward()
    optimizer.step()
    print(
        f"infidelity (loss): {loss.item()}, \n target state : "
        f"{target_state.detach().cpu().numpy()}, \n "
        f"result state : {result_state.detach().cpu().numpy()}\n"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--epochs", type=int, default=20000, help="number of training epochs"
    )

    args = parser.parse_args()

    seed = 42
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    use_cuda = torch.cuda.is_available()
    device = torch.device("cuda" if use_cuda else "cpu")

    model = QModel().to(device)

    n_epochs = args.epochs
    optimizer = optim.Adam(model.parameters(), lr=1e-2, weight_decay=0)
    scheduler = CosineAnnealingLR(optimizer, T_max=n_epochs)

    q_device = tq.QuantumDevice(n_wires=2)
    target_state = torch.tensor([0, 1, 0, 0], dtype=torch.complex64)

    for epoch in range(1, n_epochs + 1):
        print(f"Epoch {epoch}, LR: {optimizer.param_groups[0]['lr']}")
        train(target_state, q_device, model, optimizer)
        scheduler.step()


if __name__ == "__main__":
    main()
