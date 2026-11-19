# ブランチ `atf2-ext-orbit-analysis` の変更内容（machine-interfaces）

ベース：`flight-simulator-framework/machine-interfaces` の `master`（`02957e2`）
英語版：[CHANGES_atf2-ext-orbit-analysis.en.md](CHANGES_atf2-ext-orbit-analysis.en.md)

| コミット | 概要 |
|---|---|
| `f2c8890` | ATF2 Ext のビームラインの並びにある電磁石名を BPM 名に対応付ける |
| `9f8fbb3` | BPM の強度が記録されていなくても軌道を計算する |
| `126f4db` | 古い ATF2 Ext データのビームラインの並びを作り直すツールを追加 |
| `ed6386d` | ATF2 Ext の四極の PV をまとめて読む |
| `8c62217` | トラッキングモデルの更新で四極の強さが失われないようにする |

変更したファイル：`backends/atf2/machine_interfaces_atf2/InterfaceATF2_Ext.py`、`backends/atf2/machine_interfaces_atf2/repair_ext_sequence.py`（新規）、`machine_interfaces/Backend/State.py`、`tests/test_bpm_intensity.py`（新規）、`tests/test_repair_ext_sequence.py`（新規）、`tests/test_quadrupole_reads.py`（新規）

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

## 3. 古い ATF2 Ext データのビームラインの並びを作り直すツールを追加（`126f4db`）

### 問題
変更1より前に記録されたデータの並びは25項目で、BPM は2台（`MB2X`、`MSF1FF`）しか入っていません。2026-11-19 のデータで応答行列を計算すると、「最初に選んだ補正電磁石より後ろの BPM だけを使う」絞り込みで `MSF1FF` だけが残ります。この BPM は x = y = 0 を返すため、すべての DATA ペアが飛ばされ、GUI に「No complete corrector readbacks available for response-matrix.」と表示されていました。

### 変更
**`backends/atf2/machine_interfaces_atf2/InterfaceATF2_Ext.py`**
- 取り出しラインの電磁石の一覧（`EXT_SEQUENCE`）と、`ATF2:monitors` の番号と BPM 名の対応表（`MONITOR_INDEX_TO_NAME`）を、モジュールの定数にしました。
- `build_ext_sequence()` がこれらから EPICS なしで並びを作ります。`InterfaceATF2_Ext.__init__()` もこの関数を呼び、以前とまったく同じ並びになります（78項目。`MDUMP`、`IPBPM1` など12台の BPM は、これまでどおり位置が分かりません）。

**`backends/atf2/machine_interfaces_atf2/repair_ext_sequence.py`（新規）**
- データフォルダを `元のフォルダ名_sequence_fixed`（または `--out` で指定した場所）にコピーし、コピーの中の ATF2 Ext の状態ファイルすべてで `sequence` だけを書き換えます。ファイルのそれ以外の中身はそのまま残し、他のファイルもそのままコピーします。
- 元のフォルダは変更しません。コピー先がすでにあるときは処理を中止します。

```bash
python -m machine_interfaces_atf2.repair_ext_sequence ~/CERN-Flight_Simulator-Data
```

その後、GUI では `CERN-Flight_Simulator-Data_sequence_fixed` の中のフォルダを選んでください。

**`tests/test_repair_ext_sequence.py`（新規）** — 4件：補正電磁石の間に BPM が正しく並ぶこと、古い並びの BPM が残ること、修復したコピーの中身（gzip と非圧縮の pickle、他のインターフェースのファイルは変更しない、元のファイルは変更しない）、コピー先がすでにあると中止すること。

### 確認結果
- `tests/` の10件すべて成功。
- 2026-11-19 のデータ：12ファイルを修復（並び 25 → 78項目）。修復後、`ATF2_Ext_20261119_112700_Orbit` で `ZH1X` と `ZV1X` に対する応答行列が50台の BPM で計算できました。応答が最大の BPM は `MQD18X`（`ZH1X`、水平）と `MQD4BFF`（`ZV1X`、垂直）で、生データの ± の軌道差と一致します。

---

## 4. 四極の PV をまとめて読む（`ed6386d`）

**問題：** マシンの状態を記録するたび（`get_state()`。SysID なら1回振るごと）に `get_quadrupoles()` が呼ばれます。これまでは四極1台あたり最大9個の PV を順番に読み、それぞれ最大0.7秒待っていました。取り出しラインの四極21台にはムーバーが無いので、ムーバーの PV（1台6個）は決してつながらず、毎回待ち時間をすべて使っていました（約 21×6×0.7 秒 ≈ 90 秒）。

**変更**（`InterfaceATF2_Ext.py`）
- `get_quadrupoles()` は、指定された四極の PV をすべて `_pv_get_many()` でまとめて読みます。接続待ちは全体で0.7秒の期限を共有し、読み取りは並行して行います。つながらなかった PV は、次からは待ちません。CA が裏で探し続け、つながればその時点から読みます。
- `_cached_pv()` が、PV の名前ごとに `PV` オブジェクトを1つだけ作って使い回します。読むたびに作り直していたのをやめました。`auto_monitor=False` なので、`get()` は毎回その時点の値を読みます。
- `update_tracking_model_with_clibmagnet()` は、実機の値が有限で、かつモデルと違う四極だけを RF-Track のモデルに反映します。読むたびにビームを追跡し直していたのをやめました。
- 四極ごとに出ていた `'Getting quadrupoles' PVs ...` は表示しなくなりました。

読む値は以前と同じです（変更5のテストで確認）。実機での所要時間は測っていません。

---

## 5. トラッキングモデルの更新で四極の強さが失われないようにする（`8c62217`）

**問題：** `InterfaceATF2_Ext` には `log()` がありませんでした（シミュレーション版と Linac 版は `self.log = print` を設定しています）。そのため `get_quadrupoles()` からモデルを更新すると、`self.log(...)` で `AttributeError` が起きていました。このエラーは「電流から K1 への変換の失敗」として扱われ、全四極の `bdes`/`bact` が NaN で記録され、モデルも更新されていませんでした。2026-11-19 のデータ（電流は読めているのに強さが全部 NaN）と一致します。変更4だけでは直りません。強さがモデルと違う四極があると、やはりこのエラーになります。

**変更**
- `InterfaceATF2_Ext.log()` を追加しました（メッセージを表示するだけ）。GUI が `interface.log` を設定すれば、そちらが使われます。
- モデルの更新を、変換の後に独立した `try` で行うようにしました。失敗しても警告を出すだけで、強さの値は残ります。
- `tests/test_quadrupole_reads.py`（新規、偽の PV を使ったテスト6件）：まとめて読んだ値、1つずつ読んだ場合と同じ結果になること、つながらない PV を1回しか待たないこと、モデルには変わった強さだけを反映すること、モデルの更新に失敗しても強さが残ること、`log()` があること。

**確認結果：** `tests/` の16件すべて成功。この変更を外すと、新しいテスト6件のうち4件が、実機と同じメッセージ `'InterfaceATF2_Ext' object has no attribute 'log'` で失敗します。

---

## この変更では対応していない問題
- **変更1より前に記録されたデータ**は、上のツールで修復しないと、応答行列・BBA・軌道バンプで使えません。
- **値が固定された BPM**（`MFB2FF`、`MIPA`、`MIPB` が約 10 mm、`MDUMP` の y が −7.202 mm）は、位置を `status` で除外していないため、まだ軌道の平均に入ります。当面は `bpms.txt` から外してください。`status` による除外は、Ext の `status` の欄を確認してから別の変更として行うべきです。
- **`InterfaceATF2_Linac.get_bpms()`** も同じ方法（`status × 列3`）で `tmit` を計算しています。`LINAC:monitors` で強度が読めているかは未確認です。
