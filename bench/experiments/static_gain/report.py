"""Experiment 2's results for people: the printed report and plot.png."""
import matplotlib.pyplot as plt
import numpy as np

from bench import units

COLORS = {"positive": "#2a78d6", "negative": "#eb6834"}


def print_report(run_name, arm_length_m, results):
    print(f"{run_name}   L = {arm_length_m:.3f} m\n")
    print(f"{'direction':<10} {'k':>6} {'offset':>13} {'Kt':>13} {'max residual':>20} {'stiction':>13}")
    for direction, summary in results["directions"].items():
        stiction = f"{1000 * summary['static_friction_Nm']:.1f} mN·m" if "static_friction_Nm" in summary else "—"
        print(
            f"{direction:<10} {summary['k']:>6.3f} {1000 * summary['offset_Nm']:>+8.1f} mN·m"
            f" {summary['torque_constant_NmA']:>8.4f} N·m/A"
            f" {1000 * summary['max_residual_Nm']:>8.1f} mN·m ({summary['max_residual_percent']:.1f}%)"
            f" {stiction:>13}"
        )
    print()
    if "asymmetry_percent" in results:
        print(f"k = {results['k']:.3f}  (asymmetry {results['asymmetry_percent']:.1f}%)")
    else:
        print(f"k = {results['k']:.3f}  (single direction only)")
    print(f"G = {units.BELT_RATIO:g} × k = {results['G']:.3f}")
    print(
        f"Kt expected k × {results['torque_constant_configured_NmA']:.4f} (configured)"
        f" = {results['torque_constant_expected_NmA']:.4f} N·m/A"
    )
    for warning in results["warnings"]:
        print(f"Warning: {warning}")


def plot(run, fits, results, show):
    figure, (fit_axes, residual_axes) = plt.subplots(
        2, 1, sharex=True, figsize=(7, 7), height_ratios=[3, 1], layout="constrained"
    )
    limit = 1.1 * max(np.max(np.abs(direction_fit.command)) for direction_fit in fits.values())
    fit_axes.plot([-limit, limit], [-limit, limit], color="#999999", linestyle="--", linewidth=1, label="ideal (k = 1)")

    for direction, direction_fit in fits.items():
        color = COLORS[direction]
        command, torque, below = direction_fit.command, direction_fit.torque, direction_fit.from_below
        k, offset = direction_fit.summary["k"], direction_fit.summary["offset_Nm"]
        span = np.array([command[below].min(), command[below].max()])
        fit_axes.plot(span, k * span + offset, color=color, linewidth=2)
        fit_axes.plot(command[below], torque[below], "o", color=color, markersize=8, markeredgecolor="white", label=f"{direction}: k = {k:.3f}")
        if not below.all():
            fit_axes.plot(command[~below], torque[~below], "o", color=color, markersize=8, markerfacecolor="none", label=f"{direction}, from above")
        residual_axes.plot(command[below], 1000 * direction_fit.residuals, "o", color=color, markersize=8, markeredgecolor="white")

    residual_axes.axhline(0, color="#999999", linewidth=1)
    fit_axes.set_title(f"{run.name}\nk = {results['k']:.3f}, G = {results['G']:.3f}")
    fit_axes.set_ylabel("Measured torque (N·m, motor side)")
    fit_axes.legend(loc="upper left", frameon=False)
    residual_axes.set_ylabel("Residual (mN·m)")
    residual_axes.set_xlabel("Commanded torque (N·m, motor side)")
    for axes in (fit_axes, residual_axes):
        axes.grid(alpha=0.3)
        axes.spines[["top", "right"]].set_visible(False)

    figure.savefig(run.path("plot.png"), dpi=150)
    print(f"\nPlot: {run.path('plot.png')}")
    if show:
        plt.show()
