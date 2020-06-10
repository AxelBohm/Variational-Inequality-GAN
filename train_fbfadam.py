#  MIT License

# Copyright (c) Facebook, Inc. and its affiliates.

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# written by Hugo Berard (berard.hugo@gmail.com) while at Facebook.
# modifications by Axel Boehm (axel.boehm@univie.ac.at) and
# Michael Sedlmayer (michael.sedlmayer@univie.ac.at).

import torch
from torch.autograd import Variable
import time
import torchvision
import torchvision.transforms as transforms
import numpy as np
import argparse
import os
import json
import csv
import sys
import pdb

import models
import utils
from optim import FBFAdam

parser = argparse.ArgumentParser()
parser.add_argument('output')
parser.add_argument('--model', choices=('resnet', 'dcgan'), default='dcgan')
parser.add_argument('--cuda', action='store_true')
parser.add_argument('-bs', '--batch-size', default=64, type=int)
parser.add_argument('--num-iter', default=500000, type=int)
parser.add_argument('-lrd', '--learning-rate-dis', default=2e-4, type=float)
parser.add_argument('-lrg', '--learning-rate-gen', default=2e-5, type=float)
parser.add_argument('-b1', '--beta1', default=0.5, type=float)
parser.add_argument('-b2', '--beta2', default=0.9, type=float)
parser.add_argument('-ema', default=0.9999, type=float)
parser.add_argument('-nz', '--num-latent', default=128, type=int)
parser.add_argument('-nfd', '--num-filters-dis', default=128, type=int)
parser.add_argument('-nfg', '--num-filters-gen', default=128, type=int)
parser.add_argument('-gp', '--gradient-penalty', default=0, type=float)
parser.add_argument('-m', '--mode', choices=('gan', 'ns-gan', 'wgan'), default='wgan')
parser.add_argument('-c', '--clip', default=0.01, type=float)
parser.add_argument('-p', '--prox', choices=('1norm'), default='1norm')
parser.add_argument('-rp', '--reg-param', default=0, type=float)
parser.add_argument('-d', '--distribution', choices=('normal', 'uniform'), default='normal')
parser.add_argument('--batchnorm-dis', action='store_true')
parser.add_argument('--seed', default=1318, type=int)
parser.add_argument('--tensorboard', action='store_true')
parser.add_argument('--inception-score', action='store_true')
parser.add_argument('--default', action='store_true')
parser.add_argument('--inertia', default=0.0, type=float)
args = parser.parse_args()

CUDA = args.cuda
MODEL = args.model
GRADIENT_PENALTY = args.gradient_penalty
OUTPUT_PATH = args.output
TENSORBOARD_FLAG = args.tensorboard
INCEPTION_SCORE_FLAG = args.inception_score
CLIP = args.clip
PROX = args.prox
REG_PARAM = args.reg_param
INERTIA = args.inertia
DEFAULT = args.default

SEED = args.seed
torch.manual_seed(SEED)
np.random.seed(SEED)

BATCH_SIZE = args.batch_size

if DEFAULT:
    if REG_PARAM:
        config = "config/default_dcgan_wganl1_fbfadam.json"
    else:
        config = "config/default_dcgan_wgan_fbfadam.json"

    with open(config) as f:
        data = json.load(f)
    args = argparse.Namespace(**data)


# It is really important to set different learning rates for the discriminator and generator
LEARNING_RATE_G = args.learning_rate_gen
LEARNING_RATE_D = args.learning_rate_dis
N_ITER = args.num_iter
BETA_1 = args.beta1
BETA_2 = args.beta2
BETA_EMA = args.ema
N_LATENT = args.num_latent
N_FILTERS_G = args.num_filters_gen
N_FILTERS_D = args.num_filters_dis
MODE = args.mode
DISTRIBUTION = args.distribution
BATCH_NORM_G = True
BATCH_NORM_D = args.batchnorm_dis
N_SAMPLES = 50000
RESOLUTION = 32
N_CHANNEL = 3
START_EPOCH = 0
EVAL_FREQ = 10000
n_gen_update = 0
n_dis_update = 0
total_time = 0

if GRADIENT_PENALTY:
    OUTPUT_PATH = os.path.join(OUTPUT_PATH, '%s_%s-gp' % (MODEL, MODE), '%s/lrd=%.1e_lrg=%.1e/inertia=%.2f/s%i/%i' %
                               ('fbf_adam', LEARNING_RATE_D, LEARNING_RATE_G, INERTIA, SEED, int(time.time())))
elif REG_PARAM:
    OUTPUT_PATH = os.path.join(OUTPUT_PATH, '%s_%s-prox' % (MODEL, MODE),
                               '%s/lrd=%.1e_lrg=%.1e/rp=%.1e/inertia=%.2f/s%i/%i' %
                               ('fbf_adam', LEARNING_RATE_D, LEARNING_RATE_G, REG_PARAM, INERTIA, SEED,
                                int(time.time())))
else:
    OUTPUT_PATH = os.path.join(OUTPUT_PATH, '%s_%s' % (MODEL, MODE), '%s/lrd=%.1e_lrg=%.1e/inertia=%.2f/s%i/%i' %
                               ('fbf_adam', LEARNING_RATE_D, LEARNING_RATE_G, INERTIA, SEED, int(time.time())))

if TENSORBOARD_FLAG:
    from tensorboardX import SummaryWriter
    writer = SummaryWriter(log_dir=os.path.join(OUTPUT_PATH, 'tensorboard'))
    writer.add_text('config', json.dumps(vars(args), indent=2, sort_keys=True))

transform = transforms.Compose([transforms.ToTensor(), transforms.Normalize(mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5))])

trainset = torchvision.datasets.CIFAR10(root='./data', train=True, transform=transform, download=True)
trainloader = torch.utils.data.DataLoader(trainset, batch_size=BATCH_SIZE, shuffle=True, num_workers=1)

testset = torchvision.datasets.CIFAR10(root='./data', train=False, transform=transform, download=True)
testloader = torch.utils.data.DataLoader(testset, batch_size=BATCH_SIZE, num_workers=1)

print 'Init....'
if not os.path.exists(os.path.join(OUTPUT_PATH, 'checkpoints')):
    os.makedirs(os.path.join(OUTPUT_PATH, 'checkpoints'))
if not os.path.exists(os.path.join(OUTPUT_PATH, 'gen')):
    os.makedirs(os.path.join(OUTPUT_PATH, 'gen'))

if INCEPTION_SCORE_FLAG:

    from inception_score_pytorch.inception_score import inception_score

    def get_inception_score():
        all_samples = []
        samples = torch.randn(N_SAMPLES, N_LATENT)
        for i in xrange(0, N_SAMPLES, 100):
            batch_samples = samples[i:i+100].cuda(0)
            all_samples.append(gen(batch_samples).cpu().data.numpy())

        all_samples = np.concatenate(all_samples, axis=0)
        return inception_score(torch.from_numpy(all_samples), resize=True, cuda=True)

    import tflib.fid as fid
    import tensorflow as tf
    stats_path = 'tflib/data/fid_stats_cifar10_train.npz'
    inception_path = fid.check_or_download_inception('tflib/model')
    f = np.load(stats_path)
    mu_real, sigma_real = f['mu'][:], f['sigma'][:]
    f.close()

    fid.create_inception_graph(inception_path)  # load the graph into the current TF graph

    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True

    def get_fid_score():
        all_samples = []
        samples = torch.randn(N_SAMPLES, N_LATENT)
        for i in xrange(0, N_SAMPLES, BATCH_SIZE):
            samples_100 = samples[i:i+BATCH_SIZE]
            if CUDA:
                samples_100 = samples_100.cuda(0)
            all_samples.append(gen(samples_100).cpu().data.numpy())

        all_samples = np.concatenate(all_samples, axis=0)
        all_samples = np.multiply(np.add(np.multiply(all_samples, 0.5), 0.5), 255).astype('int32')
        all_samples = all_samples.reshape((-1, N_CHANNEL, RESOLUTION, RESOLUTION)).transpose(0, 2, 3, 1)

        with tf.Session(config=config) as sess:
            sess.run(tf.global_variables_initializer())
            mu_gen, sigma_gen = fid.calculate_activation_statistics(all_samples, sess, batch_size=BATCH_SIZE)

        fid_value = fid.calculate_frechet_distance(mu_gen, sigma_gen, mu_real, sigma_real)
        return fid_value

    inception_f = open(os.path.join(OUTPUT_PATH, 'inception.csv'), 'ab')
    inception_writter = csv.writer(inception_f)

if MODEL == "resnet":
    gen = models.ResNet32Generator(N_LATENT, N_CHANNEL, N_FILTERS_G, BATCH_NORM_G)
    dis = models.ResNet32Discriminator(N_CHANNEL, 1, N_FILTERS_D, BATCH_NORM_D)
elif MODEL == "dcgan":
    gen = models.DCGAN32Generator(N_LATENT, N_CHANNEL, N_FILTERS_G, batchnorm=BATCH_NORM_G)
    dis = models.DCGAN32Discriminator(N_CHANNEL, 1, N_FILTERS_D, batchnorm=BATCH_NORM_D)

if CUDA:
    gen = gen.cuda(0)
    dis = dis.cuda(0)

gen.apply(lambda x: utils.weight_init(x, mode='normal'))
dis.apply(lambda x: utils.weight_init(x, mode='normal'))

dis_optimizer = FBFAdam(dis.parameters(), lr=LEARNING_RATE_D, betas=(BETA_1, BETA_2), inertia=INERTIA)
# for generator FBF and Extragradient is the same in theory (when no projection is involved)
gen_optimizer = FBFAdam(gen.parameters(), lr=LEARNING_RATE_G, betas=(BETA_1, BETA_2), inertia=INERTIA)

with open(os.path.join(OUTPUT_PATH, 'config.json'), 'wb') as f:
    json.dump(vars(args), f)

dataiter = iter(testloader)
examples, labels = dataiter.next()
torchvision.utils.save_image(utils.unormalize(examples), os.path.join(OUTPUT_PATH, 'examples.png'), 10)

z_examples = utils.sample(DISTRIBUTION, (100, N_LATENT))
if CUDA:
    z_examples = z_examples.cuda(0)

gen_param_avg = []
gen_param_ema = []
for param in gen.parameters():
    gen_param_avg.append(param.data.clone())
    gen_param_ema.append(param.data.clone())

f = open(os.path.join(OUTPUT_PATH, 'results.csv'), 'ab')
f_writter = csv.writer(f)

print 'Training...'
numel_weights = sum(p.numel() for p in dis.parameters())
n_iteration_t = 0
gen_inception_score = 0
gen_fid_score = 0
while n_gen_update < N_ITER:
    t = time.time()
    avg_loss_G = 0
    avg_loss_D = 0
    avg_penalty = 0
    num_samples = 0
    penalty = Variable(torch.Tensor([0.]))
    if CUDA:
        penalty = penalty.cuda(0)
    for i, data in enumerate(trainloader):
        _t = time.time()
        x_true, _ = data
        x_true = Variable(x_true)

        z = Variable(utils.sample(DISTRIBUTION, (len(x_true), N_LATENT)))
        if CUDA:
            x_true = x_true.cuda(0)
            z = z.cuda(0)

        x_gen = gen(z)
        p_true, p_gen = dis(x_true), dis(x_gen)

        gen_loss = utils.compute_gan_loss(p_true, p_gen, mode=MODE)
        dis_loss = - gen_loss.clone()
        if GRADIENT_PENALTY:
            penalty = dis.get_penalty(x_true.data, x_gen.data)
            dis_loss += GRADIENT_PENALTY*penalty
        if REG_PARAM:
            L1_reg = dis.get_1norm()  # won't be differentiated
            dis_loss += L1_reg * REG_PARAM

        for p in gen.parameters():
            p.requires_grad = False
        dis_optimizer.zero_grad()
        dis_loss.backward(retain_graph=True)

        if (n_iteration_t+1) % 2 != 0:
            dis_optimizer.extrapolation()
            if MODE == 'wgan':
                nonzeros = 0.
                for p in dis.parameters():
                    if REG_PARAM:
                        if PROX == '1norm':
                            p.data = utils.prox_1norm(p.data, REG_PARAM*LEARNING_RATE_D)
                            nonzeros += p.nonzero().size(0)
                        else:
                            raise("not implemented")
                    elif not GRADIENT_PENALTY:
                        p.data.clamp_(-CLIP, CLIP)
        else:
            dis_optimizer.step()

        for p in gen.parameters():
            p.requires_grad = True

        for p in dis.parameters():
            p.requires_grad = False
        gen_optimizer.zero_grad()
        gen_loss.backward()

        if (n_iteration_t+1) % 2 != 0:
            gen_optimizer.extrapolation()
        else:
            n_gen_update += 1
            gen_optimizer.step()
            for j, param in enumerate(gen.parameters()):
                gen_param_avg[j] = gen_param_avg[j]*n_gen_update/(n_gen_update+1.) + \
                    param.data.clone()/(n_gen_update+1.)
                gen_param_ema[j] = gen_param_ema[j]*BETA_EMA + param.data.clone()*(1-BETA_EMA)

        for p in dis.parameters():
            p.requires_grad = True

        total_time += time.time() - _t

        if (n_iteration_t+1) % 2 == 0:

            avg_loss_D += dis_loss.item()*len(x_true)
            avg_loss_G += gen_loss.item()*len(x_true)
            avg_penalty += penalty.item()*len(x_true)
            num_samples += len(x_true)

            if n_gen_update % EVAL_FREQ == 1:
                if INCEPTION_SCORE_FLAG:
                    gen_inception_score = get_inception_score()[0]
                    try:
                        gen_fid_score = get_fid_score()
                    except:
                        gen_fid_score = -1

                    inception_writter.writerow((n_gen_update, gen_inception_score, gen_fid_score, total_time))
                    inception_f.flush()

                    # only generate images if IS is computed
                    x_gen = gen(z_examples)
                    x = utils.unormalize(x_gen)
                    torchvision.utils.save_image(x.data, os.path.join(OUTPUT_PATH, 'gen/%i.png' % n_gen_update), 10)

                    if TENSORBOARD_FLAG:
                        writer.add_scalar('inception_score', gen_inception_score, n_gen_update)

                torch.save({'args': vars(args), 'n_gen_update': n_gen_update,
                            'total_time': total_time, 'state_gen':
                            gen.state_dict(), 'gen_param_avg': gen_param_avg,
                            'gen_param_ema': gen_param_ema},
                           os.path.join(OUTPUT_PATH, "checkpoints/%i.state" %
                                        n_gen_update))

        n_iteration_t += 1

    avg_loss_G /= num_samples
    avg_loss_D /= num_samples
    avg_penalty /= num_samples
    nnz_perc = nonzeros/numel_weights

    if REG_PARAM:
        print 'Iter: %i, Loss Gen: %.4f, Loss Dis: %.4f, NNZ: %.2f, L1norm: %.2e, IS: %.2f, FID: %.2f, Time: %.4f' % (
            n_gen_update, avg_loss_G, avg_loss_D, nnz_perc, L1_reg*REG_PARAM,
            gen_inception_score, gen_fid_score, time.time() - t)
        f_writter.writerow((n_gen_update, avg_loss_G, avg_loss_D, nnz_perc,
                            avg_penalty, L1_reg.item()*REG_PARAM, time.time() - t))
    else:
        print 'Iter: %i, Loss Gen: %.4f, Loss Dis: %.4f, Penalty: %.2e, IS: %.2f, FID: %.2f, Time: %.4f' % (
                n_gen_update, avg_loss_G, avg_loss_D, avg_penalty,
                gen_inception_score, gen_fid_score, time.time() - t)
        f_writter.writerow((n_gen_update, avg_loss_G, avg_loss_D, nnz_perc, avg_penalty, time.time() - t))

    f.flush()

    if TENSORBOARD_FLAG:
        writer.add_scalar('loss_G', avg_loss_G, n_gen_update)
        writer.add_scalar('loss_D', avg_loss_D, n_gen_update)
        writer.add_scalar('penalty', avg_penalty, n_gen_update)

        x = torchvision.utils.make_grid(x.data, 10)
        writer.add_image('gen', x.data, n_gen_update)
