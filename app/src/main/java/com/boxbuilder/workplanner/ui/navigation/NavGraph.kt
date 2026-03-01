package com.boxbuilder.workplanner.ui.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.boxbuilder.workplanner.ui.auth.AuthScreen
import com.boxbuilder.workplanner.ui.settings.SettingsScreen
import com.boxbuilder.workplanner.ui.taskdetail.TaskDetailScreen
import com.boxbuilder.workplanner.ui.tasklist.TaskListScreen

@Composable
fun NavGraph(navController: NavHostController) {
    NavHost(
        navController = navController,
        startDestination = Screen.Auth.route
    ) {
        composable(Screen.Auth.route) {
            AuthScreen(
                onAuthComplete = {
                    navController.navigate(Screen.TaskList.route) {
                        popUpTo(Screen.Auth.route) { inclusive = true }
                    }
                }
            )
        }

        composable(Screen.TaskList.route) {
            TaskListScreen(
                onTaskClick = { taskId ->
                    navController.navigate(Screen.TaskDetail.createRoute(taskId))
                },
                onNewTask = { parentId ->
                    navController.navigate(Screen.NewTask.createRoute(parentId))
                },
                onSettingsClick = {
                    navController.navigate(Screen.Settings.route)
                }
            )
        }

        composable(
            route = Screen.TaskDetail.route,
            arguments = listOf(navArgument("taskId") { type = NavType.StringType })
        ) {
            TaskDetailScreen(
                onBack = { navController.popBackStack() },
                onTaskClick = { taskId ->
                    navController.navigate(Screen.TaskDetail.createRoute(taskId))
                },
                onNewChild = { parentId ->
                    navController.navigate(Screen.NewTask.createRoute(parentId))
                },
                onNavigateToTask = { taskId ->
                    navController.navigate(Screen.TaskDetail.createRoute(taskId)) {
                        popUpTo(Screen.TaskList.route)
                    }
                }
            )
        }

        composable(Screen.Settings.route) {
            SettingsScreen(
                onBack = { navController.popBackStack() },
                onSignedOut = {
                    navController.navigate(Screen.Auth.route) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }

        composable(
            route = "taskdetail/new?parentId={parentId}",
            arguments = listOf(navArgument("parentId") {
                type = NavType.StringType
                nullable = true
                defaultValue = null
            })
        ) {
            TaskDetailScreen(
                onBack = { navController.popBackStack() },
                onTaskClick = { taskId ->
                    navController.navigate(Screen.TaskDetail.createRoute(taskId))
                },
                onNewChild = { parentId ->
                    navController.navigate(Screen.NewTask.createRoute(parentId))
                },
                onNavigateToTask = { taskId ->
                    navController.navigate(Screen.TaskDetail.createRoute(taskId)) {
                        popUpTo(Screen.TaskList.route)
                    }
                }
            )
        }
    }
}
