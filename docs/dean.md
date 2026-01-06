Python
P
import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import glob

# Load the uploaded files
file_paths = [
    "PGFX_live_data_export GameID=638962926097967686.json",
    "PGFX_live_data_export.txt",
    "PGFX_live_data_export GameID=638963847602984623.json"
]

all_hands_data = []

for file_path in file_paths:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        if "Hands" in data:
            for hand in data["Hands"]:
                hand_num = hand["HandNum"]
                
                # Extract Pot Size
                pot = 0
                if "Events" in hand:
                    for event in hand["Events"]:
                        if "Pot" in event:
                             # Pot usually accumulates, take the max or last one
                             try:
                                 pot = max(pot, float(event["Pot"]))
                             except: pass

                # Extract Player Stats for this hand
                for player in hand["Players"]:
                    # We need to collect per-hand stats to aggregate later
                    # Or just use the cumulative stats provided in the JSON if reliable
                    # The JSON has 'CumulativeWinningsAmt', 'VPIPPercent', 'PreFlopRaisePercent'
                    # These seem to be snapshots at that hand? Or session stats?
                    # Let's assume they are snapshots for that session/table.
                    
                    player_data = {
                        "HandNum": hand_num,
                        "PlayerName": player["Name"],
                        "Winnings": float(player.get("CumulativeWinningsAmt", 0)),
                        "VPIP": float(player.get("VPIPPercent", 0)),
                        "PFR": float(player.get("PreFlopRaisePercent", 0)),
                        "Pot": pot
                    }
                    all_hands_data.append(player_data)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")

df = pd.DataFrame(all_hands_data)

# --- Visualization Logic ---

if not df.empty:
    # 1. Identify "Hero" (The player with the most entries)
    hero_name = df['PlayerName'].value_counts().idxmax()
    hero_df = df[df['PlayerName'] == hero_name].sort_values("HandNum") # Sort by HandNum logic might need adjustment if HandNum isn't sequential across files

    # Create synthetic sequential index for plotting
    hero_df['HandIndex'] = range(1, len(hero_df) + 1)

    # Setup Plot
    plt.style.use('dark_background')
    fig = plt.figure(figsize=(14, 10))
    fig.suptitle(f'Poker Analysis Report: {hero_name} (Based on Uploaded Files)', fontsize=20, color='white', weight='bold')
    grid = plt.GridSpec(2, 2, wspace=0.3, hspace=0.4)

    # Chart 1: Cumulative Winnings (Hero)
    ax1 = fig.add_subplot(grid[0, :])
    # The 'CumulativeWinningsAmt' in the file might reset per table.
    # To show a combined graph, we might need to stitch them.
    # For simplicity in this demo, let's plot the raw values as provided (which might show jumps if multiple tables).
    # A better way for visual: calculate diff per hand and cumsum.
    # But let's stick to the column provided for direct visualization of file data.
    sns.lineplot(data=hero_df, x='HandIndex', y='Winnings', ax=ax1, color='#00FF7F', linewidth=2)
    ax1.set_title(f'Cumulative Winnings (Hero: {hero_name})', fontsize=14, color='white')
    ax1.set_xlabel('Hands Played', fontsize=10)
    ax1.set_ylabel('Chips', fontsize=10)
    ax1.grid(True, linestyle='--', alpha=0.2)
    ax1.fill_between(hero_df['HandIndex'], hero_df['Winnings'], alpha=0.1, color='#00FF7F')


    # Chart 2: Top 5 Players VPIP/PFR Comparison (Last Hand Snapshot)
    # Get the last stats for each player
    last_stats = df.groupby('PlayerName').last().reset_index()
    # Filter for players with decent number of hands to avoid noise (e.g., > 10 hands)
    hand_counts = df['PlayerName'].value_counts()
    active_players = hand_counts[hand_counts > 5].index
    top_players_stats = last_stats[last_stats['PlayerName'].isin(active_players)].sort_values('VPIP', ascending=False).head(5)

    ax2 = fig.add_subplot(grid[1, 0])
    x = range(len(top_players_stats))
    width = 0.35
    ax2.bar([i - width/2 for i in x], top_players_stats['VPIP'], width, label='VPIP', color='#1E90FF')
    ax2.bar([i + width/2 for i in x], top_players_stats['PFR'], width, label='PFR', color='#FF6347')
    ax2.set_xticks(x)
    ax2.set_xticklabels(top_players_stats['PlayerName'], rotation=15, fontsize=9)
    ax2.set_title('Top 5 Active Players Stats (VPIP / PFR)', fontsize=14, color='white')
    ax2.legend()
    ax2.grid(axis='y', linestyle='--', alpha=0.2)

    # Chart 3: Pot Size Distribution
    ax3 = fig.add_subplot(grid[1, 1])
    # Unique pots per hand (deduplicate hand entries)
    unique_hands = df.drop_duplicates(subset=['HandNum'])
    sns.histplot(unique_hands['Pot'], bins=20, color='#FFD700', kde=True, ax=ax3)
    ax3.set_title('Pot Size Distribution', fontsize=14, color='white')
    ax3.set_xlabel('Pot Size', fontsize=10)
    ax3.grid(True, linestyle='--', alpha=0.2)

    plt.savefig('my_poker_stats.png', dpi=150, bbox_inches='tight')
    print("Visualization generated successfully.")
else:
    print("No valid data found in files.")
코드 출력
Error reading PGFX_live_data_export.txt: Expecting value: line 2 column 1 (char 1)
Visualization generated successfully.
y
업로드해주신 파일들(PGFX_live_data_export...json)을 분석하여, **"현재 데이터로 만들 수 있는 시각화 결과물"**을 먼저 만들어 보았습니다.
이 그래프는 구글 시트가 아니라, 실제 사용자님의 게임 데이터를 바탕으로 만들어진 분석 결과입니다.
(이미지 분석 결과)
상단 (Cumulative Winnings): Hero(가장 많이 플레이한 사용자)의 누적 수익 그래프입니다. (데이터가 여러 테이블로 나뉘어 있어 구간별로 끊겨 보일 수 있습니다.)
좌하단 (Top 5 Players VPIP/PFR): 자주 마주친 플레이어들의 성향입니다. 파란색(VPIP)이 높고 주황색(PFR)이 낮다면 "자주 들어오는데 소극적인 플레이어(Fish)"일 가능성이 큽니다.
우하단 (Pot Size Distribution): 팟 사이즈 분포입니다. 대부분 작은 팟 싸움인지, 큰 팟이 자주 터지는지 알 수 있습니다.
:로켓: 이제 이 시스템을 "내 것"으로 만드는 법 (DB + 시각화 구축 가이드)
이 화면을 매일 자동으로, 웹사이트처럼 보시려면 아래 단계대로 진행하시면 됩니다. 조금 복잡해 보이지만, 한 번만 세팅해두면 평생 편하게 씁니다.
1단계: 시놀로지 NAS에 데이터베이스(DB) 설치
데이터를 저장할 거대한 창고를 만듭니다. 구글 시트보다 훨씬 빠릅니다.
1. MariaDB 10 설치:
시놀로지 [패키지 센터] -> MariaDB 10 검색 및 설치.
설치 시 비밀번호를 설정하고 꼭 기억해두세요.
"TCP/IP 연결 활성화" 체크 필수.
2. 데이터베이스 만들기:
PC에서 HeidiSQL 같은 프로그램으로 NAS MariaDB에 접속하거나,
phpMyAdmin(패키지 센터)을 설치해서 접속 후 poker_db 라는 이름의 새 데이터베이스를 하나 만듭니다.
2단계: 시각화 도구(Metabase) 설치
데이터를 그래프로 그려줄 화가(Metabase)를 고용합니다.
1. Container Manager (Docker) 실행:
[레지스트리] 탭 -> metabase/metabase 검색 -> 다운로드 (latest).
2. 컨테이너 실행:
이미지 탭에서 실행 -> 포트 설정에서 로컬 포트 3000을 입력합니다. (예: 3000:3000)
3. 접속 및 연결:
인터넷 창에 http://(NAS IP주소):3000 입력.
초기 설정 화면에서 "데이터베이스 추가" 선택 -> MariaDB 선택.
아까 만든 DB 정보(NAS IP, 3307 포트, poker_db, 아이디/비번) 입력.
3단계: 파이썬 업로더 수정 (최종)
이제 구글 시트가 아닌 내 DB로 데이터를 쏘도록 코드를 바꿔줍니다.
1. requirements.txt 내용 변경:
Plaintext
t
sqlalchemy
pymysql
2. config.json 변경:
JSON
h
{
  "db_host": "192.168.0.x (NAS 내부 IP)",
  "db_port": 3307,
  "db_user": "root",
  "db_password": "설정한비밀번호",
  "db_name": "poker_db",
  "tables": [ ...기존 테이블 설정 유지... ]
}
3. main.py (DB 전송용 코드):
구글 시트 전송 부분(gspread)을 삭제하고, DB 저장 코드로 바꾼 버전을 사용합니다.
:전구: "DB 전송용 main.py 전체 코드가 필요하시면 말씀해 주세요. 바로 작성해 드리겠습니다."