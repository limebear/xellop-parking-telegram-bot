import time
from datetime import datetime


def parse_time(time_str):
    hours = 0
    minutes = 0

    if '시간' in time_str:
        hours = int(time_str.split('시간')[0])
        if '분' in time_str:
            minutes = int(time_str.split('시간')[1].split('분')[0])
    elif '분' in time_str:
        minutes = int(time_str.split('분')[0])

    return hours * 60 + minutes


def get_best_discount(park_time, enter_date):
    recommendations = []
    remaining_minutes = parse_time(park_time)

    # 5분 지연 딜레이를 추가
    remaining_minutes += 5

    if remaining_minutes >= 300:
        enter_date_obj = datetime.strptime(enter_date, "%Y-%m-%d %H:%M:%S")
        now_obj = datetime.now()

        if enter_date_obj.date() == now_obj.date():
            # 입차 날짜랑 출차 날짜가 같은 경우
            # 5시간 이상일 경우 당일권으로 처리
            recommendations.append(4)   # 당일권
            return recommendations
        else:
            # 입차 날짜랑 출차 날짜가 다른 경우
            # todo: 수동으로 처리하지 않도록 로직
            return recommendations
    else:
        # 아닌 경우 방문권을 미리 처리
        recommendations.append(0)  # 방문권
        remaining_minutes -= 75

        while remaining_minutes >= 0:
            if remaining_minutes >= 60:
                recommendations.append(3)  # 1시간권
                remaining_minutes -= 60
            elif remaining_minutes >= 30:
                recommendations.append(2)  # 30분권
                remaining_minutes -= 30
            elif remaining_minutes > 0:
                recommendations.append(1)  # 15분권
                remaining_minutes -= 15

    return recommendations
