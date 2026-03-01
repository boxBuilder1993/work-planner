package com.boxbuilder.workplanner.ui.navigation

import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.navArgument
import com.boxbuilder.workplanner.ui.taskdetail.TaskDetailScreen
import com.boxbuilder.workplanner.ui.tasklist.TaskListScreen

@Composable
fun NavGraph(navController: NavHostController) {
    NavHost(
        navController = navController,
        startDestination = Screen.TaskList.route
    ) {
        composable(Screen.TaskList.route) {
            TaskListScreen(
                onTaskClick = { taskId ->
                    navController.navigate(Screen.TaskDetail.createRoute(taskId))
                },
                onNewTask = { parentId ->
                    navController.navigate(Screen.NewTask.createRoute(parentId))
                },
                onSettingsClick = {
                    // TODO: Navigate to settings
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
