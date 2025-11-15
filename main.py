"""
비트코인 정밀 시황 리포트 - 텔레그램 전송
타임프레임별 개별 분석 + 문맥 기반 종합 의견
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
import requests
import os
warnings.filterwarnings('ignore')


class BTCReport:
    
    def __init__(self):
        self.data = {}
        self.report = []
        
        self.TOKEN = os.getenv('TELEGRAM_TOKEN')
        self.CHAT_ID = os.getenv('CHAT_ID')
    
    
    def log(self, text=''):
        """로그 추가"""
        self.report.append(text)
        print(text)
    
    
    def fetch_data(self, period='90d', interval='1h'):
        """yfinance로 데이터 수집"""
        print(f"수집 중: {interval} ({period})...", end=" ")
        
        try:
            btc = yf.Ticker("BTC-USD")
            df = btc.history(period=period, interval=interval)
            
            if df.empty:
                print("실패")
                return pd.DataFrame()
            
            df.columns = [c.lower() for c in df.columns]
            print(f"완료 ({len(df)}개)")
            return df
            
        except Exception as e:
            print(f"오류: {e}")
            return pd.DataFrame()
    
    
    def calc_indicators(self, df):
        """기술적 지표 계산"""
        if df.empty or len(df) < 100:
            return df
        
        # 이동평균
        df['MA7'] = df['close'].rolling(7).mean()
        df['MA20'] = df['close'].rolling(20).mean()
        df['MA50'] = df['close'].rolling(50).mean()
        df['MA99'] = df['close'].rolling(99).mean()
        df['MA200'] = df['close'].rolling(200).mean()
        
        # EMA
        df['EMA12'] = df['close'].ewm(span=12).mean()
        df['EMA26'] = df['close'].ewm(span=26).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # MACD
        df['MACD'] = df['EMA12'] - df['EMA26']
        df['MACD_signal'] = df['MACD'].ewm(span=9).mean()
        df['MACD_hist'] = df['MACD'] - df['MACD_signal']
        
        # 볼린저 밴드
        df['BB_mid'] = df['close'].rolling(20).mean()
        std = df['close'].rolling(20).std()
        df['BB_upper'] = df['BB_mid'] + (std * 2)
        df['BB_lower'] = df['BB_mid'] - (std * 2)
        df['BB_width'] = ((df['BB_upper'] - df['BB_lower']) / df['BB_mid']) * 100
        
        # ATR (변동성)
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df['ATR'] = true_range.rolling(14).mean()
        df['ATR_pct'] = (df['ATR'] / df['close']) * 100
        
        # 거래량
        df['volume_MA20'] = df['volume'].rolling(20).mean()
        
        return df
    
    
    def analyze_timeframe(self, df, tf_name):
        """타임프레임 개별 분석"""
        recent = df.dropna().tail(100)
        latest = recent.iloc[-1]
        
        close = latest['close']
        ma7 = latest['MA7']
        ma20 = latest['MA20']
        ma50 = latest['MA50']
        ma99 = latest['MA99']
        
        # 이동평균선 거리 및 기울기
        ma7_dist = ((close / ma7 - 1) * 100)
        ma20_dist = ((close / ma20 - 1) * 100)
        ma50_dist = ((close / ma50 - 1) * 100)
        
        ma20_prev = df['MA20'].iloc[-5]
        ma20_slope = ((ma20 / ma20_prev - 1) * 100)
        
        # 추세 판단
        if close > ma7 > ma20 > ma50:
            trend = "완벽한 정배열"
            trend_desc = "강한 상승 추세"
        elif close > ma7 > ma20:
            trend = "정배열"
            trend_desc = "상승 추세"
        elif close > ma50:
            trend = "장기선 위"
            trend_desc = "장기 상승세 유지"
        elif close < ma7 < ma20 < ma50:
            trend = "완벽한 역배열"
            trend_desc = "강한 하락 추세"
        elif close < ma7 < ma20:
            trend = "역배열"
            trend_desc = "하락 추세"
        else:
            trend = "혼조"
            trend_desc = "방향성 불명확"
        
        # RSI
        rsi = latest['RSI']
        rsi_percentile = (recent['RSI'] < rsi).sum() / len(recent) * 100
        
        if rsi > 70:
            rsi_status = "과매수"
            rsi_signal = "조정 압력"
        elif rsi > 60:
            rsi_status = "강세"
            rsi_signal = "상승 모멘텀"
        elif rsi > 50:
            rsi_status = "중립 상단"
            rsi_signal = "상승 우세"
        elif rsi > 40:
            rsi_status = "중립 하단"
            rsi_signal = "하락 우세"
        elif rsi > 30:
            rsi_status = "약세"
            rsi_signal = "하락 압력"
        else:
            rsi_status = "과매도"
            rsi_signal = "반등 기회"
        
        # MACD
        macd = latest['MACD']
        macd_sig = latest['MACD_signal']
        macd_hist = latest['MACD_hist']
        
        hist_prev = recent['MACD_hist'].iloc[-5]
        macd_trend = "확대" if abs(macd_hist) > abs(hist_prev) else "축소"
        macd_cross = "골든크로스" if macd > macd_sig else "데드크로스"
        
        # 볼린저 밴드
        bb_upper = latest['BB_upper']
        bb_lower = latest['BB_lower']
        bb_width = latest['BB_width']
        
        if close > bb_upper:
            bb_position = "상단 돌파 (과열)"
        elif close < bb_lower:
            bb_position = "하단 이탈 (침체)"
        else:
            bb_pct = ((close - bb_lower) / (bb_upper - bb_lower)) * 100
            if bb_pct > 80:
                bb_position = f"상단 근접 ({bb_pct:.0f}%)"
            elif bb_pct < 20:
                bb_position = f"하단 근접 ({bb_pct:.0f}%)"
            else:
                bb_position = f"중간 ({bb_pct:.0f}%)"
        
        # 거래량
        vol = latest['volume']
        vol_ma = latest['volume_MA20']
        vol_ratio = vol / vol_ma if vol_ma > 0 else 1
        
        if vol_ratio > 2.0:
            vol_status = "폭발적 증가"
        elif vol_ratio > 1.5:
            vol_status = "크게 증가"
        elif vol_ratio > 1.2:
            vol_status = "증가"
        elif vol_ratio > 0.8:
            vol_status = "보통"
        else:
            vol_status = "감소"
        
        # 변동성
        atr_pct = latest['ATR_pct']
        atr_percentile = (recent['ATR_pct'] < atr_pct).sum() / len(recent) * 100
        
        # 지지/저항
        highs = recent['high'].nlargest(5).values
        lows = recent['low'].nsmallest(5).values
        
        resistance = highs[highs > close]
        support = lows[lows < close]
        
        return {
            'close': close,
            'trend': trend,
            'trend_desc': trend_desc,
            'ma20_dist': ma20_dist,
            'ma20_slope': ma20_slope,
            'rsi': rsi,
            'rsi_status': rsi_status,
            'rsi_signal': rsi_signal,
            'rsi_percentile': rsi_percentile,
            'macd': macd,
            'macd_signal': macd_sig,
            'macd_cross': macd_cross,
            'macd_trend': macd_trend,
            'bb_upper': bb_upper,
            'bb_lower': bb_lower,
            'bb_position': bb_position,
            'vol_ratio': vol_ratio,
            'vol_status': vol_status,
            'atr_pct': atr_pct,
            'atr_percentile': atr_percentile,
            'resistance': resistance[0] if len(resistance) > 0 else None,
            'support': support[-1] if len(support) > 0 else None
        }
    
    
    def analyze(self):
        """분석"""
        # 데이터 수집
        self.data['1h'] = self.fetch_data(period='90d', interval='1h')
        
        if self.data['1h'].empty:
            self.log("❌ 데이터 수집 실패")
            return False
        
        # 4시간 리샘플링
        df_4h = self.data['1h'].resample('4H').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
        
        self.data['1d'] = self.fetch_data(period='2y', interval='1d')
        
        # 지표 계산
        self.data['1h'] = self.calc_indicators(self.data['1h'])
        self.data['4h'] = self.calc_indicators(df_4h)
        if not self.data['1d'].empty:
            self.data['1d'] = self.calc_indicators(self.data['1d'])
        
        # 현재가
        current = self.data['1h']['close'].iloc[-1]
        prev_1h = self.data['1h']['close'].iloc[-2]
        prev_24h = self.data['1h']['close'].iloc[-24]
        
        change_1h = ((current / prev_1h - 1) * 100)
        change_24h = ((current / prev_24h - 1) * 100)
        
        # 통계
        returns_7d = ((current / self.data['1d']['close'].iloc[-7] - 1) * 100) if len(self.data['1d']) > 7 else 0
        returns_30d = ((current / self.data['1d']['close'].iloc[-30] - 1) * 100) if len(self.data['1d']) > 30 else 0
        
        cummax = self.data['1d']['close'].cummax()
        drawdown = (self.data['1d']['close'] - cummax) / cummax * 100
        mdd = drawdown.min()
        current_dd = drawdown.iloc[-1]
        
        # 리포트 시작
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log("<b>📈 비트코인 정밀 시황 리포트</b>")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        self.log(f"<b>💰 현재가: ${current:,.0f}</b>")
        self.log(f"📊 1시간: {change_1h:+.2f}% | 24시간: {change_24h:+.2f}%")
        self.log(f"📉 7일: {returns_7d:+.2f}% | 30일: {returns_30d:+.2f}%")
        self.log(f"📌 현재 낙폭: {current_dd:.2f}% | 최대낙폭: {mdd:.2f}%")
        self.log()
        
        # 각 타임프레임 분석
        analysis = {}
        for tf_name, tf_key in [('1시간', '1h'), ('4시간', '4h'), ('일봉', '1d')]:
            if self.data[tf_key].empty or len(self.data[tf_key].dropna()) < 100:
                continue
            
            a = self.analyze_timeframe(self.data[tf_key], tf_name)
            analysis[tf_key] = a
            
            self.log(f"<b>▶ [{tf_name}봉] {a['trend_desc']}</b>")
            self.log(f"  추세: {a['trend']} | MA20 거리 {a['ma20_dist']:+.2f}% (기울기 {a['ma20_slope']:+.2f}%)")
            self.log(f"  <b>RSI {a['rsi']:.1f}</b> ({a['rsi_status']}) - {a['rsi_signal']} (백분위 {a['rsi_percentile']:.0f}%)")
            self.log(f"  MACD {a['macd_cross']} | 히스토그램 {a['macd_trend']}")
            self.log(f"  볼린저: {a['bb_position']} | 거래량 {a['vol_status']} ({a['vol_ratio']:.2f}배)")
            self.log(f"  변동성: ATR {a['atr_pct']:.2f}% (백분위 {a['atr_percentile']:.0f}%)")
            
            if a['resistance']:
                self.log(f"  저항: ${a['resistance']:,.0f} (+{((a['resistance']/current-1)*100):.2f}%)")
            if a['support']:
                self.log(f"  지지: ${a['support']:,.0f} ({((a['support']/current-1)*100):.2f}%)")
            
            self.log()
        
        # 종합 의견
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        self.log("<b>💡 종합 의견 및 전략</b>")
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        # 타임프레임별 상황 파악
        a1h = analysis.get('1h')
        a4h = analysis.get('4h')
        a1d = analysis.get('1d')
        
        if not all([a1h, a4h, a1d]):
            self.log("데이터 부족")
            return False
        
        # 추세 분석
        self.log("<b>1. 추세 분석</b>")
        
        if a1h['trend'] in ['완벽한 정배열', '정배열'] and a4h['trend'] in ['완벽한 정배열', '정배열'] and a1d['trend'] in ['완벽한 정배열', '정배열']:
            self.log("✅ 전 타임프레임 상승 추세 - <b>강세장</b>")
            trend_view = "강세"
        elif a1h['trend'] in ['완벽한 역배열', '역배열'] and a4h['trend'] in ['완벽한 역배열', '역배열'] and a1d['trend'] in ['완벽한 역배열', '역배열']:
            self.log("❌ 전 타임프레임 하락 추세 - <b>약세장</b>")
            trend_view = "약세"
        else:
            # 타임프레임 괴리
            if a1d['trend'] in ['완벽한 역배열', '역배열']:
                self.log(f"⚠️  <b>장기 하락세 지속</b> (일봉 {a1d['trend']})")
                if a1h['rsi'] > 50 or a4h['rsi'] > 50:
                    self.log(f"   단기 반등 시도 중 (1H RSI {a1h['rsi']:.0f} / 4H RSI {a4h['rsi']:.0f})")
                    self.log(f"   주의: 반등은 기술적 반등일 가능성. 추세 전환 아님.")
                trend_view = "약세"
            elif a1d['trend'] in ['완벽한 정배열', '정배열']:
                self.log(f"✅ <b>장기 상승세 유지</b> (일봉 {a1d['trend']})")
                if a1h['rsi'] < 50 or a4h['rsi'] < 50:
                    self.log(f"   단기 조정 중 (1H RSI {a1h['rsi']:.0f} / 4H RSI {a4h['rsi']:.0f})")
                    self.log(f"   참고: 조정은 매수 기회일 가능성.")
                trend_view = "강세"
            else:
                self.log("📊 횡보 구간 - 방향성 불명확")
                trend_view = "중립"
        
        self.log()
        
        # 모멘텀 분석
        self.log("<b>2. 모멘텀 분석</b>")
        
        # 1시간봉
        self.log(f"[단기] 1H RSI {a1h['rsi']:.0f} - {a1h['rsi_signal']}")
        
        # 4시간봉
        self.log(f"[중기] 4H RSI {a4h['rsi']:.0f} - {a4h['rsi_signal']}")
        
        # 일봉
        self.log(f"[장기] 1D RSI {a1d['rsi']:.0f} - {a1d['rsi_signal']}")
        
        # 종합 모멘텀 해석
        if a1d['rsi'] < 30:
            self.log(f"💡 <b>일봉 과매도</b> → 기술적 반등 가능성 높음")
            if a4h['rsi'] > 50:
                self.log(f"   4시간 RSI 50 돌파 → 반등 시작 신호")
            else:
                self.log(f"   4시간 RSI 아직 약세 → 반등 확인 필요")
        elif a1d['rsi'] > 70:
            self.log(f"⚠️  <b>일봉 과매수</b> → 조정 가능성 높음")
            if a4h['rsi'] < 50:
                self.log(f"   4시간 RSI 하락 → 조정 시작 신호")
        
        self.log()
        
        # 매매 전략
        self.log("<b>3. 매매 전략</b>")
        
        if trend_view == "강세":
            self.log("<b>전략: 상승 추세 편승</b>")
            self.log(f"• 매수: 조정 시 주요 지지선 근처 ({a1d['support']:,.0f} 부근)")
            self.log(f"• 목표: 저항선 돌파 시 상승 지속 ({a1d['resistance']:,.0f})")
            self.log(f"• 손절: MA20 이탈 시")
        
        elif trend_view == "약세":
            if a1d['rsi'] < 30:
                self.log("<b>전략: 과매도 반등 노림 (단기)</b>")
                self.log(f"• 조건부 진입: 4H RSI 50 돌파 + 거래량 증가 시")
                self.log(f"• 목표: 첫 저항선 ({a4h['resistance']:,.0f}) 도달 시 익절")
                self.log(f"• 손절: 지지선 이탈 시 ({a1d['support']:,.0f})")
                self.log(f"• 주의: 기술적 반등이므로 욕심 금지")
            else:
                self.log("<b>전략: 관망 또는 반등 매도</b>")
                self.log(f"• 반등 시 저항선 ({a4h['resistance']:,.0f}) 근처에서 매도")
                self.log(f"• 4H RSI 50 이상 유지 시 추세 전환 가능성 확인")
                self.log(f"• 신규 진입은 일봉 정배열 전환 후 고려")
        
        else:
            self.log("<b>전략: 관망</b>")
            self.log(f"• 방향성 명확해질 때까지 대기")
            self.log(f"• 상방: {a1d['resistance']:,.0f} 돌파 시 매수")
            self.log(f"• 하방: {a1d['support']:,.0f} 이탈 시 관망 지속")
        
        self.log()
        
        # 주의사항
        self.log("<b>4. 주의사항</b>")
        
        risks = []
        
        if a1d['vol_ratio'] > 2.0:
            risks.append(f"거래량 급증 ({a1d['vol_ratio']:.1f}배) - 변동성 확대 예상")
        
        if a1d['atr_percentile'] > 80:
            risks.append(f"높은 변동성 (ATR 백분위 {a1d['atr_percentile']:.0f}%) - 리스크 관리 필수")
        
        if abs(current_dd) > 20:
            risks.append(f"고점 대비 {abs(current_dd):.0f}% 낙폭 - 심리적 저항")
        
        if a1h['macd_cross'] != a4h['macd_cross']:
            risks.append(f"MACD 괴리 (1H {a1h['macd_cross']} vs 4H {a4h['macd_cross']}) - 방향성 불일치")
        
        if risks:
            for r in risks:
                self.log(f"⚠️  {r}")
        else:
            self.log("특이사항 없음")
        
        self.log()
        self.log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        return True
    
    
    def send_telegram(self):
        """텔레그램 전송"""
        if not self.TOKEN or not self.CHAT_ID:
            print("텔레그램 설정 없음")
            return
        
        message = '\n'.join(self.report)
        
        url = f"https://api.telegram.org/bot{self.TOKEN}/sendMessage"
        data = {
            "chat_id": self.CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        
        try:
            r = requests.post(url, data=data, timeout=10)
            if r.status_code == 200:
                print("\n✅ 텔레그램 전송 완료")
            else:
                print(f"\n❌ 전송 실패: {r.status_code}")
        except Exception as e:
            print(f"\n❌ 오류: {e}")
    
    
    def run(self):
        """실행"""
        print("\n비트코인 정밀 리포트 생성 시작\n")
        success = self.analyze()
        
        if success:
            self.send_telegram()
            print("\n완료")
        else:
            print("\n실패")
            if self.report:
                self.send_telegram()


if __name__ == "__main__":
    report = BTCReport()
    report.run()