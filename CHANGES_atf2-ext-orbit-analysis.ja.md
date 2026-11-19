# ブランチ `atf2-ext-orbit-analysis` の変更内容（machine-interfaces）

ベース：`flight-simulator-framework/machine-interfaces` の `master`（`02957e2`）
英語版：[CHANGES_atf2-ext-orbit-analysis.en.md](CHANGES_atf2-ext-orbit-analysis.en.md)

| コミット | 概要 |
|---|---|
| `f2c8890` | ATF2 Ext のビームラインの並びにある電磁石名を BPM 名に対応付ける |
| `9f8fbb3` | BPM の強度が記録されていなくても軌道を計算する |

変更したファイル：`backends/atf2/machine_interfaces_atf2/InterfaceATF2_Ext.py`、`machine_interfaces/Backend/State.py`、`tests/test_bpm_intensity.py`（新規）

---

## 1. ATF2 Ext のビームラインの並びにある電磁石名を BPM 名に対応付ける（`f2c8890`）

**ファイル：** `backends/atf2/machine_interfaces_atf2/InterfaceATF2_Ext.py`（`__init__`）

**問題：** ビームラインの並び（sequence）には電磁石の名前（`QF1X`、`FB2FF`、`IPB`）が並んでいます。一方 `ATF2:monitors` では、その位置の BPM を `M<電磁石名>`（`MQF1X`、`MFB2FF`、`MIPB`）と呼びます。これまでのコードは、名前がそのまま BPM 名と一致する項目しか残さなかったため、記録される並びからほとんどの BPM が抜け落ちていました。その結果、`sequence.index()` で機器を並べるアプリ（応答行列、BBA、軌道バンプ）が BPM の位置を特定できませんでした。

**変更：**
- 並びの各項目を BPM 名に変換します（`MONITOR_INDEX_TO_NAME` にある方の `X` または `MX`）。補正電磁石（`Z*`）はそのまま残します。
- `atf2_full_twiss.tfs` に合わせて、先頭に `MB1X` を加え、`QM11FF` の前に `FB1FF` を挿入します。
- 重複を取り除き、それでも位置が分からない BPM を表示します。

---

## 2. BPM の強度が記録されていなくても軌道を計算する（`9f8fbb3`）

### 問題
- 取り出しライン（Ext）では `ATF2:monitors` の BPM 強度の欄が空で、全BPMで0が返ります（PV で確認済み。DR の monitors では強度が読めています）。
- `InterfaceATF2_Ext.get_bpms()` は `tmit = status × 強度` と計算していたため、全スナップショットが `tmit = 0` で保存されていました。
- 2026-10-19 のコミット `d985519` 以降、`State.get_orbit()` は `tmit` が正のショットだけを残します。`tmit` が全部0なので全ショットが捨てられ、67台すべての BPM が NaN（故障扱い）になっていました。

### 修正前の影響
- 保存済みの ATF2 Ext のデータ（2026-11-19 の `ATF2_Ext_*_Orbit` フォルダなど）からは、SysID、BBA、軌道バンプ、応答行列のどれでも軌道が得られませんでした。
- **実機の SysID での危険：** 軌道が全部 NaN だと応答が0と判定され、`update_amplitude()` が振り幅を毎回約1.4倍に増やし、上限電流まで大きくなり続けます。プロットも空のままになります。
- 既存のテストは仮データで `tmit = 1` を使っていたため、この問題を検出できませんでした。

### 変更

**`machine_interfaces/Backend/State.py` — `State.get_orbit()`**
- どれか1台でも正の強度が記録されている場合：動作は変わりません。強度がない、または低い（その BPM の中央値の半分未満）ショットは捨てます。
- どの BPM にも正の強度がない場合：`RuntimeWarning`（「BPM intensity (tmit) is not recorded …」）を出し、ショットを捨てずに全ショットを平均します。
- 全部 NaN の列で `nanmedian` が出していた `RuntimeWarning` は表示しないようにしました。

**`backends/atf2/machine_interfaces_atf2/InterfaceATF2_Ext.py` — `get_bpms()`**
- サンプルごとに、どの BPM にも正の強度がなければ、`tmit` を 0（ビームなし）ではなく NaN（未計測）で記録します。読み取り後にメッセージを1回表示します。
- 判定はサンプル単位で全 BPM をまとめて行います。他の BPM で強度が読めていれば、本当にビームが届かなかった BPM は従来どおり0で記録されます。
- 位置（`x`、`y`）は変更していません。これまでどおり `status` に関係なく記録されます。

**`tests/test_bpm_intensity.py`（新規、pytest）**

| テスト | 確認内容 |
|---|---|
| `test_orbit_without_recorded_intensity_keeps_every_shot[zero]` / `[nan]` | `tmit` が全部0または全部 NaN → 全ショットの平均が軌道になり、警告が出る |
| `test_orbit_with_recorded_intensity_still_drops_shots_without_beam` | 強度が記録されていれば、`tmit = 0` のショットは従来どおり捨てられる |
| `test_orbit_with_recorded_intensity_flags_bpm_without_beam` | ビームが一度も届かない BPM は従来どおり故障扱いになる |
| `test_ext_records_missing_intensity_as_nan` | 偽の `ATF2:monitors` で強度が空のとき、`InterfaceATF2_Ext.get_bpms()` の `tmit` が NaN になり、軌道が計算できる |
| `test_ext_keeps_reported_intensity_and_status` | 強度が読めているときは従来どおり `status × 強度` が記録される |

実行方法：

```bash
python -m pip install pytest
python -m pytest tests -q
```

### 確認結果
- 修正後：6件すべて成功。修正を外した状態（`State.py` と `InterfaceATF2_Ext.py` を元に戻した状態）では、バグを再現する3件が失敗し、従来の動作を確かめる3件は成功します。
- 2026-11-19 の ATF2 Ext データで `State.get_orbit()` を実行した結果：

  | | 軌道が出た BPM | 故障扱い |
  |---|---|---|
  | 修正前 | 0 / 67 | 67 |
  | 修正後 | 43 / 67 | 24（x = y = 0 ちょうどの値を返す BPM） |

---

## この変更では対応していない問題
- **2026-11-19 のデータからは、まだ応答行列を計算できません。** このデータに記録されている並びは変更1より前に書かれたもので、BPM が2台（`MB2X`、`MSF1FF`、どちらも値が0）しか入っていません。このブランチで記録したデータでは起きないはずですが、既存のデータを使うには並びを作り直す必要があります。
- **値が固定された BPM**（`MFB2FF`、`MIPA`、`MIPB` が約 10 mm、`MDUMP` の y が −7.202 mm）は、位置を `status` で除外していないため、まだ軌道の平均に入ります。当面は `bpms.txt` から外してください。`status` による除外は、Ext の `status` の欄を確認してから別の変更として行うべきです。
- **`InterfaceATF2_Linac.get_bpms()`** も同じ方法（`status × 列3`）で `tmit` を計算しています。`LINAC:monitors` で強度が読めているかは未確認です。
