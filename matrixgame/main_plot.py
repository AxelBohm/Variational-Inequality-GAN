import numpy as np
import matplotlib.pyplot as plt
# from helpers import *
from optim import FBF

#rand_seed = 42
rand_seed = 9001
np.random.seed(seed=rand_seed)

# problem formulation
d = int(5e02)
# diag = np.random.rand(d)
diag = np.random.choice([-1.,1.], d)
A = np.diag(diag)
a = np.random.rand(d)
b = np.random.rand(d)
x_sol = np.linalg.solve(A.transpose(),-b)
y_sol = np.linalg.solve(A, -a)

rp_x = 1e01
reg_x = '1norm'
rp_y = 1e02
reg_y = '2norm'
# print("Rank A:", np.linalg.matrix_rank(A))


M = np.block([
	[np.zeros((d,d)), A],
	[-A.transpose(),  np.zeros((d,d))]
])
L = np.linalg.norm(M)
print("Lipschitz constant: ", L)

# Parameters for experiments
batch_size = 0
max_iter = 1e5
eps = 1e-10
LR = 1/L
x0 = np.random.rand(d)
y0 = np.random.rand(d)

#markers = ["o", "v", "p", "*", "d"]
#line_styles = ["solid", "dotted", "dashed", "dashdot", (0, (3, 1, 1, 1, 1, 1))]


#fig_fp, ax_fp = plt.subplots(figsize=(8,7))
#fig_gap, ax_gap = plt.subplots(figsize=(8,7))

x, y, time, iter, Error_fp, Error_gap = FBF(A=A, a=a, b=b, rp_x=rp_x, rp_y=rp_y, x0=x0, y0=y0, LR=LR, reg_x=reg_x, reg_y=reg_y, batch_size=batch_size, max_iter=max_iter, eps=eps)

print("Min/Max component x_sol:", min(x_sol), max(x_sol))
print("Min/Max component y_sol:", min(y_sol), max(y_sol))
print("Min/Max component x:", min(x), max(x))
print("Min/Max component y:", min(y), max(y))
print("Norm distance x: ", np.linalg.norm(x-x_sol))
print("Norm distance y: ", np.linalg.norm(y-y_sol))
#ax_fp.plot(np.arange(iter), Error_fp) #, label = r'$\rho = {:.2f}; \alpha = {:.2f}$'.format(rho, a), linestyle=line_styles[i])#, marker = markers[i])
#ax_gap.plot(np.arange(iter), Error_gap) #, label = r'$\rho = {:.2f}; \alpha = {:.2f}$'.format(rho, a), linestyle=line_styles[i])

#ax_fp.legend()
#ax_fp.set_xscale("log")
#ax_fp.set_yscale("log")
#ax_fp.set_title("Error behaviour $\Vert y_k - z_k \Vert$; Projections onto unit balls")
#fig_fp.savefig("./figures/Error_fp_{}_ball_{}.png".format(rand_seed, tol))

#ax_gap.legend()
#ax_gap.set_xscale("log")
#ax_gap.set_yscale("log")
#ax_gap.set_title(r"Gap function $G(\theta_k, \varphi_k)$; Projections onto unit balls")
#fig_gap.savefig("./figures/Gap_function_{}_ball_{}.png".format(rand_seed, tol))

#plt.show()


