#!/usr/bin/env python3
"""将 ECMWF Reduced Gaussian Grid（缩减高斯网格，Oxxx）转换为规则经纬度网格。

该文件主要用于“整套网格处理”：
- ReducedGaussianGrid：提供 O320/O1280 的网格索引与经纬度坐标生成
- GaussianToRegularConverter：将一维的高斯网格数据插值到规则经纬度网格（SciPy）

依赖：
- 必需：numpy
- 插值：scipy（仅在调用转换函数时需要）
- 可视化：matplotlib（仅在调用可视化函数时需要）
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

import numpy as np


class GaussianGridType(str, Enum):
    """高斯网格类型（ECMWF Reduced Gaussian Grid，'O' family）。"""

    O320 = "o320"
    O1280 = "o1280"

    @property
    def latitude_lines(self) -> int:
        """半球纬度线数量 L。总纬线数为 2L。"""
        if self is GaussianGridType.O320:
            return 320
        if self is GaussianGridType.O1280:
            return 1280
        raise ValueError(f"不支持的高斯网格类型: {self.value}")

    @property
    def count(self) -> int:
        """总点数（ECMWF 'O' 缩减高斯网格）。"""
        l: int = self.latitude_lines
        return 4 * l * (l + 9)

    def nx_of(self, y: int) -> int:
        """纬度线 y 上的经度点数（y 范围：0..2L-1）。"""
        l: int = self.latitude_lines
        if y < 0 or y >= 2 * l:
            raise ValueError(f"y 超出范围: y={y}, 期望 0..{2 * l - 1}")
        if y < l:
            return 20 + y * 4
        return (2 * l - y - 1) * 4 + 20

    def integral(self, y: int) -> int:
        """纬度线 y 之前所有点的累计数量（前缀和）。"""
        l: int = self.latitude_lines
        if y < 0 or y > 2 * l:
            raise ValueError(f"y 超出范围: y={y}, 期望 0..{2 * l}")
        if y <= l:
            # y == l 时也适用（上半球全部）
            return 2 * y * y + 18 * y
        # 镜像对称（匹配 Swift 实现）
        remaining: int = 2 * l - y
        return self.count - (2 * remaining * remaining + 18 * remaining)


def _wrap_longitude(lon: float) -> float:
    """将经度标准化到 [-180, 180)。"""
    return ((lon + 180.0) % 360.0) - 180.0


def _round_away_from_zero(x: float) -> int:
    """远离零的舍入（匹配 Swift 的 round() 行为：ties away from zero）。"""
    if x >= 0.0:
        return int(np.floor(x + 0.5))
    return int(np.ceil(x - 0.5))


@dataclass(frozen=True)
class ReducedGaussianGrid:
    """缩减高斯网格（Reduced Gaussian Grid）的索引与坐标工具。"""

    grid_type: GaussianGridType

    def _dy(self) -> float:
        """纬度线间距（度）。"""
        l: int = self.grid_type.latitude_lines
        return 180.0 / (2.0 * float(l) + 0.5)

    def find_point(self, lat: float, lon: float) -> int:
        """找到最接近给定经纬度的网格点索引（在一维数据数组中的下标）。"""
        x, y = self.find_point_xy(lat=lat, lon=lon)
        return self.grid_type.integral(y) + x

    def find_point_xy(self, lat: float, lon: float) -> Tuple[int, int]:
        """找到最接近给定经纬度的网格点 (x, y) 坐标。"""
        l: int = self.grid_type.latitude_lines
        dy: float = self._dy()

        # 计算纬线索引
        y_raw: float = float(l) - 1.0 - ((lat - dy / 2.0) / dy)
        y: int = max(0, min(2 * l - 2, int(y_raw)))
        y_upper: int = y + 1

        nx: int = self.grid_type.nx_of(y)
        nx_upper: int = self.grid_type.nx_of(y_upper)
        dx: float = 360.0 / float(nx)
        dx_upper: float = 360.0 / float(nx_upper)

        lon_wrapped: float = _wrap_longitude(lon)
        x0: int = _round_away_from_zero(lon_wrapped / dx)
        x1: int = _round_away_from_zero(lon_wrapped / dx_upper)

        point_lat: float = float(l - y - 1) * dy + dy / 2.0
        point_lon: float = float(x0) * dx
        point_lat_upper: float = float(l - y_upper - 1) * dy + dy / 2.0
        point_lon_upper: float = float(x1) * dx_upper

        dist0: float = (point_lat - lat) ** 2 + (point_lon - lon_wrapped) ** 2
        dist1: float = (point_lat_upper - lat) ** 2 + (point_lon_upper - lon_wrapped) ** 2

        if dist0 < dist1:
            return ((x0 + nx) % nx, y)
        return ((x1 + nx_upper) % nx_upper, y_upper)

    def get_lat_lon_arrays(self) -> Tuple[np.ndarray, np.ndarray]:
        """获取所有网格点的经纬度坐标。

        Returns:
            (lats, lons): 两个一维数组，长度为 `grid_type.count`，与数据一维索引一致。
        """
        l: int = self.grid_type.latitude_lines
        dy: float = self._dy()

        total: int = self.grid_type.count
        lats: np.ndarray = np.empty(total, dtype=np.float64)
        lons: np.ndarray = np.empty(total, dtype=np.float64)

        for y in range(2 * l):
            start: int = self.grid_type.integral(y)
            nx: int = self.grid_type.nx_of(y)
            end: int = start + nx

            lat: float = float(l - y - 1) * dy + dy / 2.0
            dx: float = 360.0 / float(nx)

            lats[start:end] = lat
            lon_line: np.ndarray = np.arange(nx, dtype=np.float64) * dx
            # 标准化到 [-180, 180)
            lon_line = ((lon_line + 180.0) % 360.0) - 180.0
            lons[start:end] = lon_line

        return lats, lons

    def get_grid_info(self) -> dict[str, float | int | str]:
        """获取网格信息（便于调试/日志）。"""
        l: int = self.grid_type.latitude_lines
        dy: float = self._dy()
        return {
            "grid_type": self.grid_type.value,
            "latitude_lines": 2 * l,
            "total_points": self.grid_type.count,
            "dy": dy,
            "lat_min": -(float(l) * dy - dy / 2.0),
            "lat_max": float(l) * dy - dy / 2.0,
        }


class GaussianToRegularConverter:
    """将缩减高斯网格数据转换为规则经纬度网格。"""

    def __init__(self, grid_type: GaussianGridType):
        self.grid: ReducedGaussianGrid = ReducedGaussianGrid(grid_type=grid_type)
        self._lats_src: Optional[np.ndarray] = None
        self._lons_src: Optional[np.ndarray] = None

    def _get_source_coords(self) -> Tuple[np.ndarray, np.ndarray]:
        """获取源网格坐标（缓存）。"""
        if self._lats_src is None or self._lons_src is None:
            self._lats_src, self._lons_src = self.grid.get_lat_lon_arrays()
        return self._lats_src, self._lons_src

    def to_regular_grid(
        self,
        data: np.ndarray,
        target_resolution: Tuple[float, float] = (0.25, 0.25),
        lat_range: Optional[Tuple[float, float]] = None,
        lon_range: Optional[Tuple[float, float]] = None,
        method: str = "linear",
        fill_value: float = np.nan,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """将缩减高斯网格数据插值到规则经纬度网格。

        Args:
            data: 一维数据数组，长度必须等于 `grid_type.count`
            target_resolution: 目标网格分辨率 (dlat, dlon)，单位：度
            lat_range: 纬度范围 (lat_min, lat_max)，默认为高斯网格覆盖范围
            lon_range: 经度范围 (lon_min, lon_max)，默认为 [-180, 180]
            method: 插值方法，可选 'linear', 'nearest', 'cubic'
            fill_value: 插值区域外的填充值

        Returns:
            (lats_2d, lons_2d, lat_1d, lon_1d, data_2d)
        """
        dlat, dlon = target_resolution
        if dlat <= 0.0 or dlon <= 0.0:
            raise ValueError(f"target_resolution 必须为正数，得到: {target_resolution}")

        expected_count: int = self.grid.grid_type.count
        if int(data.shape[0]) != expected_count:
            raise ValueError(
                f"数据长度不匹配: 期望 {expected_count} 个点，实际得到 {int(data.shape[0])} 个点"
            )

        # 延迟导入，避免仅导入模块就强制依赖 SciPy
        try:
            from scipy.interpolate import NearestNDInterpolator, griddata  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise SystemExit(
                "缺少依赖：scipy。请安装：`pip install scipy`，或改用不需要 SciPy 的实现。"
            ) from exc

        lats_src, lons_src = self._get_source_coords()

        info = self.grid.get_grid_info()
        if lat_range is None:
            lat_min: float = float(info["lat_min"])
            lat_max: float = float(info["lat_max"])
        else:
            lat_min, lat_max = lat_range

        if lon_range is None:
            lon_min: float = -180.0
            lon_max: float = 180.0
        else:
            lon_min, lon_max = lon_range

        # 规则网格坐标（包含边界：+d/2 以减少浮点误差导致的缺失）
        lat_1d: np.ndarray = np.arange(lat_min, lat_max + dlat / 2.0, dlat, dtype=np.float64)
        lon_1d: np.ndarray = np.arange(lon_min, lon_max + dlon / 2.0, dlon, dtype=np.float64)
        lons_2d, lats_2d = np.meshgrid(lon_1d, lat_1d)

        points_src: np.ndarray = np.column_stack([lons_src, lats_src])
        points_tgt: np.ndarray = np.column_stack([lons_2d.ravel(), lats_2d.ravel()])

        if method == "nearest":
            interpolator = NearestNDInterpolator(points_src, data)
            data_interp: np.ndarray = np.asarray(interpolator(points_tgt), dtype=np.float64)
        else:
            data_interp = griddata(
                points_src,
                data,
                points_tgt,
                method=method,
                fill_value=fill_value,
            )
            data_interp = np.asarray(data_interp, dtype=np.float64)

        data_2d: np.ndarray = data_interp.reshape(lats_2d.shape)
        return lats_2d, lons_2d, lat_1d, lon_1d, data_2d

    def to_regular_grid_fast(
        self,
        data: np.ndarray,
        target_lats: np.ndarray,
        target_lons: np.ndarray,
    ) -> np.ndarray:
        """快速转换到指定的规则网格（仅最近邻，SciPy）。

        适用于目标网格坐标已知/可复用的情况（例如批量处理多变量数据）。
        """
        if target_lats.shape != target_lons.shape:
            raise ValueError(f"target_lats/target_lons 形状不一致: {target_lats.shape} vs {target_lons.shape}")

        expected_count: int = self.grid.grid_type.count
        if int(data.shape[0]) != expected_count:
            raise ValueError(
                f"数据长度不匹配: 期望 {expected_count} 个点，实际得到 {int(data.shape[0])} 个点"
            )

        try:
            from scipy.interpolate import NearestNDInterpolator  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise SystemExit("缺少依赖：scipy。请安装：`pip install scipy`。") from exc

        lats_src, lons_src = self._get_source_coords()
        points_src: np.ndarray = np.column_stack([lons_src, lats_src])
        interpolator = NearestNDInterpolator(points_src, data)

        points_tgt: np.ndarray = np.column_stack([target_lons.ravel(), target_lats.ravel()])
        data_interp: np.ndarray = np.asarray(interpolator(points_tgt), dtype=np.float64)
        return data_interp.reshape(target_lats.shape)


def example_usage() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """示例：如何使用转换器（生成模拟数据并转换）。"""
    grid_type: GaussianGridType = GaussianGridType.O320
    total_points: int = grid_type.count

    # 假设这是从 OM 文件读取到的一维高斯网格数据
    data_gaussian: np.ndarray = np.random.randn(total_points).astype(np.float64)

    converter = GaussianToRegularConverter(grid_type=grid_type)

    lats_2d, lons_2d, lat_1d, lon_1d, data_2d = converter.to_regular_grid(
        data=data_gaussian,
        target_resolution=(0.25, 0.25),
        method="linear",
    )

    print(f"原始高斯网格: {total_points} 个点")
    print(f"规则网格形状: {data_2d.shape}")
    print(f"纬度范围: {lat_1d[0]:.2f} 到 {lat_1d[-1]:.2f}")
    print(f"经度范围: {lon_1d[0]:.2f} 到 {lon_1d[-1]:.2f}")

    # 区域示例（中国区域）
    lats_2d_cn, lons_2d_cn, lat_1d_cn, lon_1d_cn, data_2d_cn = converter.to_regular_grid(
        data=data_gaussian,
        target_resolution=(0.1, 0.1),
        lat_range=(15.0, 55.0),
        lon_range=(70.0, 140.0),
        method="linear",
    )
    print(f"\n中国区域网格形状: {data_2d_cn.shape}")
    _ = (lats_2d_cn, lons_2d_cn, lat_1d_cn, lon_1d_cn)  # 仅示例，避免未使用变量的误解

    return data_2d, lats_2d, lons_2d


def visualize_comparison(
    data_gaussian: np.ndarray,
    grid_type: GaussianGridType,
    save_path: str = "gaussian_vs_regular.png",
) -> None:
    """可视化对比原始高斯网格和转换后的规则网格（需要 matplotlib）。"""
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("缺少依赖：matplotlib。请安装：`pip install matplotlib`。") from exc

    grid = ReducedGaussianGrid(grid_type=grid_type)
    lats_gaussian, lons_gaussian = grid.get_lat_lon_arrays()

    converter = GaussianToRegularConverter(grid_type=grid_type)
    lats_2d, lons_2d, _lat_1d, _lon_1d, data_2d = converter.to_regular_grid(
        data=data_gaussian,
        target_resolution=(0.5, 0.5),
        method="linear",
    )

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))

    sc1 = axes[0].scatter(
        lons_gaussian,
        lats_gaussian,
        c=data_gaussian,
        s=1,
        cmap="viridis",
    )
    axes[0].set_title(f"原始缩减高斯网格 ({grid_type.value})\n总点数: {len(data_gaussian)}")
    axes[0].set_xlabel("经度")
    axes[0].set_ylabel("纬度")
    plt.colorbar(sc1, ax=axes[0])

    im = axes[1].pcolormesh(
        lons_2d,
        lats_2d,
        data_2d,
        cmap="viridis",
        shading="auto",
    )
    axes[1].set_title(f"规则经纬度网格\n形状: {data_2d.shape}")
    axes[1].set_xlabel("经度")
    axes[1].set_ylabel("纬度")
    plt.colorbar(im, ax=axes[1])

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"对比图已保存到: {save_path}")
    plt.close(fig)


def main() -> int:
    """直接运行本文件时的演示入口。"""
    print("=== 缩减高斯网格转换示例 ===\n")

    data_2d, _lats_2d, _lons_2d = example_usage()
    _ = data_2d

    try:
        grid_type: GaussianGridType = GaussianGridType.O320
        data_gaussian: np.ndarray = np.random.randn(grid_type.count).astype(np.float64)
        visualize_comparison(data_gaussian, grid_type)
    except SystemExit:
        # 已在错误信息中提示缺少依赖
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

