from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from vcbet.core.ledger_manager import normalize_ledger_schema


def _read_ledger(path: str | Path) -> pd.DataFrame:
    df = normalize_ledger_schema(pd.read_csv(path, sep=';'))
    for col in [
        'stake_units', 'result_units_model', 'result_units_real', 'odd_entrada',
        'ev_percent', 'confidence_score', 'final_odd_fechamento'
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def _split_flags(series: pd.Series) -> pd.Series:
    return (
        series.fillna('SEM_FLAG')
        .astype(str)
        .str.split('|')
        .explode()
        .replace('', 'SEM_FLAG')
    )


def _print_block(title: str, obj: pd.DataFrame | pd.Series):
    print(f"\n=== {title} ===")
    if isinstance(obj, pd.Series):
        print(obj.to_string())
    else:
        print(obj.to_string(index=False))


def build_report(df: pd.DataFrame, run_id: str | None = None) -> None:
    if run_id:
        df = df[df['run_id'].astype(str) == run_id].copy()

    if df.empty:
        print('Nenhuma linha encontrada para o filtro informado.')
        return

    settled = df[df.get('final_bet_status', pd.Series(index=df.index)).astype(str).isin(['settled', 'voided', 'cancelled'])].copy()
    pending = df[~df.index.isin(settled.index)].copy()

    print(f"Linhas totais: {len(df)}")
    print(f"Liquidadas: {len(settled)}")
    print(f"Pendentes: {len(pending)}")

    if 'result_units_model' in settled.columns:
        model_units = settled['result_units_model'].fillna(0).sum()
        model_stake = settled['stake_units'].fillna(0).sum()
        model_roi = (model_units / model_stake * 100) if model_stake else 0.0
        print(f"Resultado modelo (u): {model_units:.2f}")
        print(f"Stake total modelo (u): {model_stake:.2f}")
        print(f"ROI modelo (%): {model_roi:.2f}")

    if 'bet_executed' in settled.columns:
        real = settled[settled['bet_executed'].astype(str).str.lower() == 'yes'].copy()
        if not real.empty and 'result_units_real' in real.columns:
            real_units = real['result_units_real'].fillna(0).sum()
            real_stake = pd.to_numeric(real.get('stake_units_executada'), errors='coerce').fillna(0).sum()
            real_roi = (real_units / real_stake * 100) if real_stake else 0.0
            print(f"Resultado real (u): {real_units:.2f}")
            print(f"Stake total real (u): {real_stake:.2f}")
            print(f"ROI real (%): {real_roi:.2f}")

    if not settled.empty:
        _print_block('Liquidação por status', settled['final_settlement_status'].fillna('pending').value_counts())

        by_market = (
            settled.groupby('market_type', dropna=False)
            .agg(
                picks=('bet_id', 'count'),
                stake=('stake_units', 'sum'),
                units=('result_units_model', 'sum'),
                avg_ev=('ev_percent', 'mean'),
                avg_odd=('odd_entrada', 'mean'),
            )
            .reset_index()
        )
        by_market['roi_percent'] = by_market.apply(
            lambda r: (r['units'] / r['stake'] * 100) if r['stake'] else 0.0, axis=1
        )
        _print_block('Performance por mercado', by_market.sort_values('units', ascending=False))

        by_stake = (
            settled.groupby('stake_units', dropna=False)
            .agg(picks=('bet_id', 'count'), stake=('stake_units', 'sum'), units=('result_units_model', 'sum'))
            .reset_index()
        )
        by_stake['roi_percent'] = by_stake.apply(
            lambda r: (r['units'] / r['stake'] * 100) if r['stake'] else 0.0, axis=1
        )
        _print_block('Performance por stake', by_stake.sort_values('stake_units'))

        by_conf = (
            settled.groupby('confidence_score', dropna=False)
            .agg(picks=('bet_id', 'count'), stake=('stake_units', 'sum'), units=('result_units_model', 'sum'))
            .reset_index()
        )
        by_conf['roi_percent'] = by_conf.apply(
            lambda r: (r['units'] / r['stake'] * 100) if r['stake'] else 0.0, axis=1
        )
        _print_block('Performance por confiança', by_conf.sort_values('confidence_score'))

        flag_series = _split_flags(settled.get('risk_flags', pd.Series(index=settled.index, dtype='object')))
        flag_df = settled[['bet_id', 'result_units_model']].copy()
        flag_df['risk_flag'] = flag_series.values
        by_flag = (
            flag_df.groupby('risk_flag', dropna=False)
            .agg(picks=('bet_id', 'count'), units=('result_units_model', 'sum'))
            .reset_index()
            .sort_values(['units', 'picks'], ascending=[False, False])
        )
        _print_block('Performance por flag', by_flag)

        if 'final_odd_fechamento' in settled.columns:
            clv_df = settled.dropna(subset=['final_odd_fechamento']).copy()
            if not clv_df.empty:
                clv_df['clv_delta'] = clv_df['odd_entrada'] - clv_df['final_odd_fechamento']
                print(f"\nCLV médio (odd_entrada - odd_fechamento): {clv_df['clv_delta'].mean():.4f}")
                print(f"Picks com closing capturada: {len(clv_df)}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Relatório do ledger')
    parser.add_argument('--ledger-file', required=True, help='Caminho do bets_ledger.csv')
    parser.add_argument('--run-id', help='Filtra uma run específica')
    args = parser.parse_args()

    df = _read_ledger(args.ledger_file)
    build_report(df, run_id=args.run_id)
