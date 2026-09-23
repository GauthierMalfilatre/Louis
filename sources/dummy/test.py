import pygame

WIDTH, HEIGHT = 800, 600
SPEED = 5

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Test bot")
clock = pygame.time.Clock()

player = pygame.Rect(WIDTH // 2, HEIGHT // 2, 50, 50)
enemy = pygame.Rect(100, 100, 50, 50)
enemy_dx = 3
enemy_dy = 3

running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    keys = pygame.key.get_pressed()
    if keys[pygame.K_LEFT]:
        player.x -= SPEED
    if keys[pygame.K_RIGHT]:
        player.x += SPEED
    if keys[pygame.K_UP]:
        player.y -= SPEED
    if keys[pygame.K_DOWN]:
        player.y += SPEED

    enemy.x += enemy_dx
    enemy.y += enemy_dy
    if enemy.left < 0 or enemy.right > WIDTH:
        enemy_dx = -enemy_dx
    if enemy.top < 0 or enemy.bottom > HEIGHT:
        enemy_dy = -enemy_dy

    if player.colliderect(enemy):
        print("Touché !")

    screen.fill((20, 20, 30))
    pygame.draw.rect(screen, (0, 200, 0), player)
    pygame.draw.rect(screen, (200, 0, 0), enemy)
    pygame.display.flip()

    clock.tick(60)

pygame.quit()
