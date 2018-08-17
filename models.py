from copy import deepcopy

import torch
import torch.nn as nn
import torch.nn.functional as F

import numpy as np

from util import to_numpy

if torch.cuda.is_available():
    FloatTensor = torch.cuda.FloatTensor
else:
    FloatTensor = torch.FloatTensor


class RLNN(nn.Module):

    def __init__(self, state_dim, action_dim, max_action):
        super(RLNN, self).__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.max_action = max_action

    def set_params(self, params):
        """
        Set the params of the network to the given parameters
        """
        cpt = 0
        for param in self.parameters():
            tmp = np.product(param.size())

            if torch.cuda.is_available():
                param.data.copy_(torch.from_numpy(
                    params[cpt:cpt + tmp]).view(param.size()).cuda())
            else:
                param.data.copy_(torch.from_numpy(
                    params[cpt:cpt + tmp]).view(param.size()))
            cpt += tmp

    def train_actor(self, critic, memory, batch_size):
        """
        Computes gradient of actor wrt given critic
        """

        # Sample replay buffer
        x, _, _, _, _ = memory.sample(batch_size)
        state = FloatTensor(x)

        # Compute actor loss
        actor_loss = -critic(state, self.forward(state)).mean()

        # Optimize the actor
        actor_loss.backward()

        return self.get_grads()

    def get_params(self):
        """
        Returns parameters of the actor
        """
        return deepcopy(np.hstack([to_numpy(v).flatten() for v in
                                   self.parameters()]))

    def get_grads(self):
        """
        Returns the current gradient
        """
        return deepcopy(np.hstack([to_numpy(v.grad).flatten() for v in self.parameters()]))

    def get_size(self):
        """
        Returns the number of parameters of the network
        """
        return self.get_params().shape[0]

    def load_model(self, filename, net_name):
        """
        Loads the model
        """
        if filename is None:
            return

        self.load_state_dict(
            torch.load('{}/{}.pkl'.format(filename, net_name))
        )

    def save_model(self, output, net_name):
        """
        Saves the model
        """
        torch.save(
            self.state_dict(),
            '{}/{}.pkl'.format(output, net_name)
        )


class ActorERL(RLNN):

    def __init__(self, state_dim, action_dim, max_action, init=False):
        super(ActorERL, self).__init__(state_dim, action_dim, max_action)

        self.l1 = nn.Linear(state_dim, 128)
        self.n1 = nn.LayerNorm(128)

        self.l2 = nn.Linear(128, 128)
        self.n2 = nn.LayerNorm(128)

        self.l3 = nn.Linear(128, action_dim)

        self.max_action = max_action
        if init:
            self.l3.weight.data.mul_(0.1)
            self.l3.bias.data.mul_(0.1)

    def forward(self, x):

        x = F.tanh(self.n1(self.l1(x)))
        x = F.tanh(self.n2(self.l2(x)))
        x = F.tanh(self.l3(x))

        return self.max_action * x


class CriticERL(RLNN):
    def __init__(self, state_dim, action_dim):
        super(CriticERL, self).__init__(state_dim, action_dim, 1)

        self.l1 = nn.Linear(state_dim, 128)
        self.l2 = nn.Linear(action_dim, 128)

        self.l3 = nn.Linear(256, 256)
        self.n3 = nn.LayerNorm(256)

        self.l4 = nn.Linear(256, 1)
        self.l4.weight.data.mul_(0.1)
        self.l4.bias.data.mul_(0.1)

    def forward(self, x, u):

        x = F.elu(self.l1(x))
        u = F.elu(self.l2(u))
        x = torch.cat((x, u), 1)

        x = F.elu(self.n3(self.l3(x)))
        x = self.l4(x)

        return x


class CriticTD3ERL(RLNN):
    def __init__(self, state_dim, action_dim):
        super(CriticTD3ERL, self).__init__(state_dim, action_dim, 1)

        # Q1 architecture
        self.l1 = nn.Linear(state_dim, 128)
        self.l2 = nn.Linear(action_dim, 128)

        self.l3 = nn.Linear(256, 256)
        self.n3 = nn.LayerNorm(256)

        self.l4 = nn.Linear(256, 1)
        self.l4.weight.data.mul_(0.1)
        self.l4.bias.data.mul_(0.1)

        # Q2 architecture
        self.l5 = nn.Linear(state_dim, 128)
        self.l6 = nn.Linear(action_dim, 128)

        self.l7 = nn.Linear(256, 256)
        self.n7 = nn.LayerNorm(256)

        self.l8 = nn.Linear(256, 1)
        self.l8.weight.data.mul_(0.1)
        self.l8.bias.data.mul_(0.1)

    def forward(self, x, u):

        x1 = F.elu(self.l1(x))
        u1 = F.elu(self.l2(u))
        x1 = torch.cat((x1, u1), 1)

        x1 = F.elu(self.n3(self.l3(x1)))
        x1 = self.l4(x1)

        x2 = F.elu(self.l5(x))
        u2 = F.elu(self.l6(u))
        x2 = torch.cat((x2, u2), 1)

        x2 = F.elu(self.n7(self.l7(x2)))
        x2 = self.l8(x2)

        return x1, x2


class Critic(RLNN):
    def __init__(self, state_dim, action_dim, layer_norm=False):
        super(Critic, self).__init__(state_dim, action_dim, 1)

        self.l1 = nn.Linear(state_dim + action_dim, 400)
        self.l2 = nn.Linear(400, 300)
        self.l3 = nn.Linear(300, 1)

        if layer_norm:
            self.n1 = nn.LayerNorm(400)
            self.n2 = nn.LayerNorm(300)
        self.layer_norm = layer_norm

    def forward(self, x, u):

        if not self.layer_norm:
            x = F.relu(self.l1(torch.cat([x, u], 1)))
            x = F.relu(self.l2(x))
            x = self.l3(x)

        else:
            x = F.relu(self.n1(self.l1(torch.cat([x, u], 1))))
            x = F.relu(self.n2(self.l2(x)))
            x = self.l3(x)

        return x


class Actor(RLNN):

    def __init__(self, state_dim, action_dim, max_action, layer_norm=False, init=True):
        super(Actor, self).__init__(state_dim, action_dim, max_action)

        self.l1 = nn.Linear(state_dim, 400)
        self.l2 = nn.Linear(400, 300)
        self.l3 = nn.Linear(300, action_dim)

        if layer_norm:
            self.n1 = nn.LayerNorm(400)
            self.n2 = nn.LayerNorm(300)
        self.layer_norm = layer_norm

    def forward(self, x):

        if not self.layer_norm:
            x = F.relu(self.l1(x))
            x = F.relu(self.l2(x))
            x = self.max_action * F.tanh(self.l3(x))

        else:
            x = F.relu(self.n1(self.l1(x)))
            x = F.relu(self.n2(self.l2(x)))
            x = self.max_action * F.tanh(self.l3(x))

        return x


class CriticTD3(RLNN):
    def __init__(self, state_dim, action_dim, layer_norm=False):
        super(CriticTD3, self).__init__(state_dim, action_dim, 1)

        # Q1 architecture
        self.l1 = nn.Linear(state_dim + action_dim, 400)
        self.l2 = nn.Linear(400, 300)
        self.l3 = nn.Linear(300, 1)

        if layer_norm:
            self.n1 = nn.LayerNorm(400)
            self.n2 = nn.LayerNorm(300)

        # Q2 architecture
        self.l4 = nn.Linear(state_dim + action_dim, 400)
        self.l5 = nn.Linear(400, 300)
        self.l6 = nn.Linear(300, 1)

        if layer_norm:
            self.n4 = nn.LayerNorm(400)
            self.n5 = nn.LayerNorm(300)
        self.layer_norm = layer_norm

    def forward(self, x, u):

        if not self.layer_norm:
            x1 = F.relu(self.l1(torch.cat([x, u], 1)))
            x1 = F.relu(self.l2(x1))
            x1 = self.l3(x1)

        else:
            x1 = F.relu(self.n1(self.l1(torch.cat([x, u], 1))))
            x1 = F.relu(self.n2(self.l2(x1)))
            x1 = self.l3(x1)

        if not self.layer_norm:
            x2 = F.relu(self.l4(torch.cat([x, u], 1)))
            x2 = F.relu(self.l5(x2))
            x2 = self.l6(x2)

        else:
            x2 = F.relu(self.n4(self.l4(torch.cat([x, u], 1))))
            x2 = F.relu(self.n5(self.l5(x2)))
            x2 = self.l6(x2)

        return x1, x2