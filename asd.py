from scipy.optimize import minimize

# Nelson-Siegel-Svensson model
def nelson_siegel_svensson(t, beta0, beta1, beta2, beta3, tau1, tau2):
    term1 = (1 - np.exp(-t / tau1)) / (t / tau1)
    term2 = term1 - np.exp(-t / tau1)
    term3 = ((1 - np.exp(-t / tau2)) / (t / tau2)) - np.exp(-t / tau2)
    return beta0 + beta1 * term1 + beta2 * term2 + beta3 * term3

# Loss function to minimize
def loss(params, t, y):
    beta0, beta1, beta2, beta3, tau1, tau2 = params
    y_hat = nelson_siegel_svensson(t, beta0, beta1, beta2, beta3, tau1, tau2)
    return np.mean((y - y_hat) ** 2)

# Initial parameters guess
initial_guess = [10, -5, 5, -2, 1.0, 2.0]

# Fit the model
opt_result = minimize(loss, initial_guess, args=(df["Duration"].values, df["TIREA"].values), method='L-BFGS-B')

# Generate fitted curve
duration_range = np.linspace(min(df["Duration"]), max(df["Duration"]), 200)
fitted_yield = nelson_siegel_svensson(duration_range, *opt_result.x)

# Plotting
plt.figure(figsize=(12, 7))
plt.plot(duration_range, fitted_yield, label="Nelson-Siegel-Svensson Fit", color="red")
plt.scatter(df["Duration"], df["TIREA"], color="blue")

# Annotate each bond with its code
for i, row in df.iterrows():
    plt.annotate(row["Código"], (row["Duration"], row["TIREA"]),
                 textcoords="offset points", xytext=(0, 5), ha='center', fontsize=8)

plt.title("Curva de Rendimiento - Ajuste Nelson-Siegel-Svensson")
plt.xlabel("Duration (años)")
plt.ylabel("TIREA (%)")
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()
