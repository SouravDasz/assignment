class Emplooye:
    def __init__(self):
        self.id=1
        self.salary=50000
        self.name="sde"
    def bonus(self):
        return self.salary*0.2
ankan=Emplooye()

print(ankan.salary)
print(ankan.bonus())