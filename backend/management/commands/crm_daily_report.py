# backend/management/commands/crm_daily_report.py
"""
Команда для генерації щоденного CRM звіту
Використання: python manage.py crm_daily_report
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Sum, Avg, Q
from backend.models import Client, ClientInteraction, ClientTask, Lead, LeadPaymentOperation


class Command(BaseCommand):
    help = 'Генерує щоденний звіт по CRM активності'

    def handle(self, *args, **options):
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)

        self.stdout.write(f"📊 CRM Звіт за {today}")
        self.stdout.write("=" * 50)

        # Статистика по клієнтах
        total_clients = Client.objects.count()
        new_clients_today = Client.objects.filter(created_at__date=today).count()
        akb_clients = Client.objects.filter(total_orders__gt=0).count()

        self.stdout.write(f"\n👥 КЛІЄНТИ:")
        self.stdout.write(f"   Всього в базі: {total_clients}")
        self.stdout.write(f"   Нових сьогодні: {new_clients_today}")
        self.stdout.write(f"   АКБ клієнтів: {akb_clients}")

        # Розподіл по температурі
        temp_stats = Client.objects.values('temperature').annotate(
            count=Count('id')
        ).order_by('temperature')

        self.stdout.write(f"\n🌡️ ТЕМПЕРАТУРА ЛІДІВ:")
        for stat in temp_stats:
            temp_name = dict(Client.TEMPERATURE_CHOICES).get(stat['temperature'], stat['temperature'])
            self.stdout.write(f"   {temp_name}: {stat['count']}")

        # Розподіл по сегментах АКБ
        akb_stats = Client.objects.filter(
            akb_segment__in=['vip', 'premium', 'standard', 'basic']
        ).values('akb_segment').annotate(
            count=Count('id'),
            revenue=Sum('total_spent')
        ).order_by('-revenue')

        self.stdout.write(f"\n💰 СЕГМЕНТИ АКБ:")
        for stat in akb_stats:
            segment_name = dict(Client.AKB_SEGMENT_CHOICES).get(stat['akb_segment'], stat['akb_segment'])
            revenue = stat['revenue'] or 0
            self.stdout.write(f"   {segment_name}: {stat['count']} клієнтів, {revenue:.0f} грн")

        # Активність взаємодій
        interactions_today = ClientInteraction.objects.filter(created_at__date=today)
        interactions_week = ClientInteraction.objects.filter(created_at__date__gte=week_ago)

        self.stdout.write(f"\n📞 ВЗАЄМОДІЇ:")
        self.stdout.write(f"   Сьогодні: {interactions_today.count()}")
        self.stdout.write(f"   За тиждень: {interactions_week.count()}")

        # ТОП активні менеджери сьогодні
        top_managers = interactions_today.values(
            'created_by__username'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:5]

        if top_managers:
            self.stdout.write(f"\n🏆 ТОП АКТИВНІ МЕНЕДЖЕРИ:")
            for i, manager in enumerate(top_managers, 1):
                self.stdout.write(f"   {i}. {manager['created_by__username']}: {manager['count']} взаємодій")

        # Задачі
        pending_tasks = ClientTask.objects.filter(status='pending').count()
        overdue_tasks = ClientTask.objects.filter(
            due_date__lt=timezone.now(),
            status__in=['pending', 'in_progress']
        ).count()
        completed_today = ClientTask.objects.filter(
            completed_at__date=today,
            status='completed'
        ).count()

        self.stdout.write(f"\n📋 ЗАДАЧІ:")
        self.stdout.write(f"   Очікують виконання: {pending_tasks}")
        self.stdout.write(f"   Прострочено: {overdue_tasks}")
        self.stdout.write(f"   Завершено сьогодні: {completed_today}")

        # Фінансова статистика
        revenue_today = LeadPaymentOperation.objects.filter(
            created_at__date=today,
            operation_type='received'
        ).aggregate(total=Sum('amount'))['total'] or 0

        revenue_week = LeadPaymentOperation.objects.filter(
            created_at__date__gte=week_ago,
            operation_type='received'
        ).aggregate(total=Sum('amount'))['total'] or 0

        self.stdout.write(f"\n💵 ФІНАНСИ:")
        self.stdout.write(f"   Виручка сьогодні: {revenue_today:.2f} грн")
        self.stdout.write(f"   Виручка за тиждень: {revenue_week:.2f} грн")

        # Ризикові клієнти
        churn_risk = Client.objects.filter(
            Q(temperature='sleeping') | Q(rfm_recency__gt=180),
            total_orders__gt=0
        ).count()

        potential_loss = Client.objects.filter(
            Q(temperature='sleeping') | Q(rfm_recency__gt=180),
            total_orders__gt=0
        ).aggregate(total=Sum('total_spent'))['total'] or 0

        self.stdout.write(f"\n⚠️ РИЗИКИ:")
        self.stdout.write(f"   Клієнтів з ризиком відтоку: {churn_risk}")
        self.stdout.write(f"   Потенційні втрати: {potential_loss:.2f} грн")

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(f"📅 Звіт згенеровано: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
