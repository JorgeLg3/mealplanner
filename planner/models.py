from django.db import models

from recipes.models import Recipe


class MealType(models.TextChoices):
    LUNCH = "lunch", "Lunch"
    DINNER = "dinner", "Dinner"


class Weekday(models.IntegerChoices):
    MONDAY = 1, "Monday"
    TUESDAY = 2, "Tuesday"
    WEDNESDAY = 3, "Wednesday"
    THURSDAY = 4, "Thursday"
    FRIDAY = 5, "Friday"
    SATURDAY = 6, "Saturday"
    SUNDAY = 7, "Sunday"


class TemplateWeek(models.Model):
    """A reusable Mon–Sun plan"""

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_featured = models.BooleanField(default=False)
    featured_order = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return self.name


class RealWeek(models.Model):
    """A concrete week on the calendar, identified by its Monday. A snapshot:
    independent of any template once its meals are created."""

    start_date = models.DateField(unique=True)

    def __str__(self):
        return f"Week of {self.start_date:%Y-%m-%d}"


class Meal(models.Model):
    """Shared shape of a single planned slot. Abstract: each subclass gets its
    own standalone table"""

    meal_type = models.CharField(max_length=20, choices=MealType.choices)
    weekday = models.IntegerField(choices=Weekday.choices)
    recipe = models.ForeignKey(Recipe, on_delete=models.PROTECT)

    class Meta:
        abstract = True


class TemplateMeal(Meal):
    template = models.ForeignKey(
        TemplateWeek, on_delete=models.CASCADE, related_name="meals"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template", "weekday", "meal_type"],
                name="unique_template_slot",
            )
        ]

    def __str__(self):
        return (
            f"{self.template}: {self.get_weekday_display()} "
            f"{self.get_meal_type_display()}"
        )


class RealMeal(Meal):
    week = models.ForeignKey(RealWeek, on_delete=models.CASCADE, related_name="meals")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["week", "weekday", "meal_type"],
                name="unique_realweek_slot",
            )
        ]

    def __str__(self):
        return (
            f"{self.week}: {self.get_weekday_display()} {self.get_meal_type_display()}"
        )
